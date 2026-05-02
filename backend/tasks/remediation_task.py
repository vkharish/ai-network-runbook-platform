"""Celery task — execute approved remediation steps on network devices.

Runs only the steps with approval_status == "approved".
Updates each step's execution_status and execution_output in-place (JSONB).
Sets plan.status to "completed" or "failed" when done.
"""

import asyncio
from datetime import datetime, timezone

from backend.tasks.celery_worker import celery_app
from backend.core.logging import get_logger

log = get_logger(__name__)


@celery_app.task(bind=True, max_retries=0, name="tasks.execute_remediation_plan")
def execute_remediation_plan(self, plan_id: str) -> dict:
    """Execute approved remediation steps for a plan."""
    return asyncio.run(_run(plan_id))


async def _run(plan_id: str) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from backend.core.config import settings
    from backend.models.remediation_model import RemediationPlan

    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    results = {"plan_id": plan_id, "steps_executed": [], "final_status": ""}

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(RemediationPlan).where(RemediationPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if not plan:
            log.error("remediation_plan_not_found", plan_id=plan_id)
            return results

        inc_id = str(plan.incident_id)
        log.info("remediation_execution_start", plan_id=plan_id, incident_id=inc_id)

        updated_steps = list(plan.steps)
        any_failed = False

        for i, step in enumerate(updated_steps):
            if step.get("approval_status") != "approved":
                continue

            step = dict(step)
            device_name = step["device"]
            command = step["command"]
            step["execution_status"] = "executing"
            updated_steps[i] = step
            plan.steps = list(updated_steps)
            await db.flush()

            log.info(
                "remediation_step_executing",
                plan_id=plan_id,
                step=step["step_number"],
                device=device_name,
                command=command,
            )

            output, success = await _execute_command(device_name, command)
            now = datetime.now(timezone.utc).isoformat()
            step["execution_output"] = output[:2000] if len(output) > 2000 else output
            step["executed_at"] = now
            step["execution_status"] = "completed" if success else "failed"
            updated_steps[i] = step
            plan.steps = list(updated_steps)
            await db.flush()

            results["steps_executed"].append({
                "step_number": step["step_number"],
                "device": device_name,
                "command": command,
                "success": success,
            })

            if not success:
                any_failed = True
                log.warning(
                    "remediation_step_failed",
                    plan_id=plan_id,
                    step=step["step_number"],
                    device=device_name,
                    output=output[:200],
                )

        plan.status = "failed" if any_failed else "completed"
        results["final_status"] = plan.status
        await db.commit()

        log.info(
            "remediation_execution_complete",
            plan_id=plan_id,
            incident_id=inc_id,
            status=plan.status,
        )

    await engine.dispose()
    return results


async def _execute_command(device_name: str, command: str) -> tuple[str, bool]:
    """Run a single command via DeviceGateway. Returns (output, success)."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select
        from backend.core.config import settings
        from backend.models.device_model import Device
        from backend.automation.device_gateway import run_command

        engine = create_async_engine(settings.database_url, echo=False)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Device).where(Device.hostname == device_name)
            )
            device = result.scalar_one_or_none()

        await engine.dispose()

        if not device:
            return f"Device '{device_name}' not found in inventory.", False

        output = await asyncio.to_thread(run_command, device, command)
        return output, True

    except Exception as exc:
        log.error("remediation_command_error", device=device_name, command=command, error=str(exc))
        return str(exc), False
