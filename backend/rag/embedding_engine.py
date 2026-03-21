"""Embedding engine abstraction — supports OpenAI and SentenceTransformers."""

from abc import ABC, abstractmethod
from typing import List

from backend.core.config import EmbeddingProvider, settings
from backend.core.logging import get_logger

log = get_logger(__name__)


class BaseEmbeddingEngine(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts and return a list of float vectors."""
        ...

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class OpenAIEmbeddingEngine(BaseEmbeddingEngine):
    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self._model = settings.embedding_model
        log.info("openai_embedding_engine_ready", model=self._model)

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]


class SentenceTransformerEmbeddingEngine(BaseEmbeddingEngine):
    """Uses fastembed (ONNX Runtime) — no PyTorch required, Python 3.13 compatible."""

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=settings.embedding_model)
        log.info("fastembed_engine_ready", model=settings.embedding_model)

    def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = list(self._model.embed(texts))
        return [e.tolist() for e in embeddings]


# Module-level singleton — initialised lazily on first use.
_engine: BaseEmbeddingEngine | None = None


def get_embedding_engine() -> BaseEmbeddingEngine:
    global _engine
    if _engine is None:
        if settings.embedding_provider == EmbeddingProvider.OPENAI:
            _engine = OpenAIEmbeddingEngine()
        else:
            _engine = SentenceTransformerEmbeddingEngine()
    return _engine
