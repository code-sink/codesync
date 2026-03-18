import asyncio
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.StateTracker import repo_manager, activity_feed
from app.db.db import AsyncSessionLocal
from app.db.models.models import Repository, UserAccess

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["Activity"])

async def _get_repo_key(repo_id: int, user_id: int) -> str | None:
    """Verify user has access to this repo and return its owner/name key."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(Repository)
            .join(UserAccess, Repository.repository_id == UserAccess.c.repo_id)
            .where(
                UserAccess.c.user_id == user_id,
                Repository.repository_id == repo_id
            )
        )
        repo = result.scalar_one_or_none()
        return repo.repo_name if repo else None

@router.get("/repos/{repo_id}/stream/{branch_name}")
async def activity_stream(repo_id: int, branch_name: str, request: Request):
    """
    SSE endpoint : Webapp will connect here to receive live activity snapshots
    for a specific repo. Sends updates on a fixed timer.
    """
    current_user = request.state.user
    repo_key = await _get_repo_key(repo_id, current_user.user_id)

    if not repo_key:
        return StreamingResponse(
            iter(['data: {"error": "repo not found"}\n\n']),
            media_type="text/event-stream"
        )

    sub_key = f"{repo_key}:{branch_name}"
    queue = activity_feed.subscribe(sub_key)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # wait for a message, timeout after 30s
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # send a comment to prevent connection timeout
                    yield ": keepalive\n\n"
        finally:
            activity_feed.unsubscribe(repo_key, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/repos/{repo_id}/snapshot")
async def activity_snapshot(repo_id: int, request: Request):
    """
    HTTP endpoint for on-demand refresh. Webapp calls this when user
    manually requests an update without waiting for the next SSE push.
    """
    current_user = request.state.user
    repo_key = await _get_repo_key(repo_id, current_user.user_id)

    if not repo_key:
        return {"error": "repo not found"}

    owner, repo_name = repo_key.split("/", 1)
    snapshot = repo_manager.get_active_devs(owner, repo_name)
    return {"repo": repo_key, "active_devs": snapshot}