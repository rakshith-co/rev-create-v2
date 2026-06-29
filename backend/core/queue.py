import asyncio
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Coroutine, Any

from repos import dlq as dlq_repo
from repos import creatives as creatives_repo

logger = logging.getLogger("revCreate.queue")

PIPELINE_TIMEOUT = float(os.getenv("PIPELINE_TIMEOUT", "600.0"))

pipeline_semaphore = asyncio.Semaphore(int(os.getenv("PIPELINE_CONCURRENCY", "5")))
image_semaphore = asyncio.Semaphore(int(os.getenv("IMAGE_GEN_CONCURRENCY", "8")))

# ── Cancellation registry ─────────────────────────────────────────────────────
_cancel_flags: dict[str, asyncio.Event] = {}


def register_cancel_flag(job_id: str) -> asyncio.Event:
    flag = asyncio.Event()
    _cancel_flags[job_id] = flag
    return flag


def request_cancellation(job_id: str) -> bool:
    """Set the cancel flag for a job. Returns True if the job was running."""
    flag = _cancel_flags.get(job_id)
    if flag:
        flag.set()
        return True
    return False


def unregister_cancel_flag(job_id: str) -> None:
    _cancel_flags.pop(job_id, None)


async def handle_task_failure(
    job_id: str, 
    creative_ids: list[str], 
    task_name: str, 
    error: Exception, 
    payload: dict | None = None
) -> None:
    """Marks creatives as failed and records the failure in the DLQ."""
    error_msg = str(error)
    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    
    # 1. Update the creative documents
    if creative_ids:
        for cid in creative_ids:
            await creatives_repo.update(
                cid,
                {"status": "failed", "error_message": error_msg},
            )
        
    # 2. Add to DLQ (Dead Letter Queue)
    try:
        await dlq_repo.insert({
            "job_id": job_id,
            "creative_ids": creative_ids,
            "task_name": task_name,
            "error_message": error_msg,
            "traceback": trace,
            "payload": payload or {},
            "failed_at": datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error("Failed to insert into DLQ: %s", e)


async def execute_pipeline_task(
    job_id: str,
    task_name: str,
    context: Any,
    coro: Coroutine[Any, Any, None]
) -> None:
    """
    Executes a pipeline coroutine with a strict timeout and DLQ integration.
    Ensures the context state is marked as FAILED if an unhandled exception or timeout occurs.
    """
    from core.pipeline import PipelineState
    try:
        await asyncio.wait_for(coro, timeout=PIPELINE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("%s timed out after %s seconds — job=%s", task_name, PIPELINE_TIMEOUT, job_id)
        context.state = PipelineState.FAILED
        await handle_task_failure(
            job_id, 
            context.creative_ids, 
            task_name, 
            Exception(f"Pipeline timed out after {PIPELINE_TIMEOUT} seconds")
        )
    except Exception as exc:
        logger.error("%s failed — job=%s error=%s", task_name, job_id, exc)
        context.state = PipelineState.FAILED
        await handle_task_failure(job_id, context.creative_ids, task_name, exc)
