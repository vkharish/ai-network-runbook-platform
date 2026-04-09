"""pytest configuration — async test client, in-memory SQLite DB, mock LLM."""

import json
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite doesn't have JSONB — map it to JSON so in-memory tests work
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from backend.database.base import Base
from backend.database.session import get_db
from backend.main import create_app

# ---------------------------------------------------------------------------
# In-memory SQLite engine (no Postgres required for tests)
# ---------------------------------------------------------------------------
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        json_serializer=json.dumps,
        json_deserializer=json.loads,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_client(test_engine):
    """Return an httpx AsyncClient wired to the FastAPI app with in-memory DB."""
    SessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession,
        expire_on_commit=False, autoflush=False,
    )

    async def override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Mock LLM client — returns hardcoded valid JSON for AnalysisAgent/ReportAgent
# ---------------------------------------------------------------------------
MOCK_ANALYSIS_JSON = json.dumps({
    "root_cause": "BGP hold timer expired due to interface flap",
    "hypothesis": "Interface GigabitEthernet1 flapped causing BGP hold timer to expire.",
    "confidence": 0.85,
    "evidence": ["BGP state was Active in CLI output"],
    "affected_components": ["R1-CORE GigabitEthernet1"],
    "urgency": "high",
})

MOCK_REPORT_JSON = json.dumps({
    "summary": "BGP session dropped on R1-CORE due to interface instability.",
    "steps": ["1. Check interface status: show interface GigabitEthernet1",
              "2. Verify BGP session: show bgp summary"],
    "commands": ["show bgp summary", "show interface GigabitEthernet1"],
    "escalation": "Escalate to Tier 3 if not resolved in 30 minutes.",
})


@pytest.fixture()
def mock_llm(monkeypatch):
    """Replace get_llm_client() with a stub that returns canned JSON."""
    from backend.agents.llm_client import BaseLLMClient

    class StubLLMClient(BaseLLMClient):
        def complete(self, messages, temperature=0.2, max_tokens=2048) -> str:
            # Return analysis JSON if prompt contains "urgency", else report JSON
            prompt = " ".join(m.get("content", "") for m in messages)
            if "urgency" in prompt:
                return MOCK_ANALYSIS_JSON
            return MOCK_REPORT_JSON

    monkeypatch.setattr(
        "backend.agents.llm_client.get_llm_client",
        lambda: StubLLMClient(),
    )
    monkeypatch.setattr(
        "backend.agents.analysis_agent.get_llm_client",
        lambda: StubLLMClient(),
    )
    monkeypatch.setattr(
        "backend.agents.report_agent.get_llm_client",
        lambda: StubLLMClient(),
    )


# ---------------------------------------------------------------------------
# Helper: register a user and return auth header
# ---------------------------------------------------------------------------
async def register_and_login(client: AsyncClient, email: str, password: str) -> dict:
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "full_name": "Test User",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
