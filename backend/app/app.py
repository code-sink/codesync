import json
import logging
import time
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from .StateTracker.RepoManager import RepoManager
from .StateTracker.GithubAPI import File
from .StateTracker.FileStates import PatchEvent
from .utls import parse_update
from app.routes import auth
from app.routes import user_repos
from app.routes import webhooks
from app.routes import activity
from .db.db import create_all_tables
from app.middleware.auth_middleware import AuthMiddleware, get_current_user_ws

from .StateTracker import repo_manager

app = FastAPI()
app.add_middleware(AuthMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await create_all_tables()
    asyncio.create_task(periodic_activity_push())

app.include_router(auth.router)
app.include_router(user_repos.router)
app.include_router(webhooks.router)
app.include_router(activity.router)

@app.websocket("/developer-updates")
async def developer_updates(websocket: WebSocket, user = Depends(get_current_user_ws)):
    """
    Single persistent WebSocket connection per developer session.

    Expected message format (JSON):
    {
        "type": "patch_update" | "branch_update" | "base_commit_update",
        ...type-specific fields (see below)...
    }

    --- patch_update ---
    Sent whenever a developer saves / auto-saves a file change.
    {
        "type":        "patch_update",
        "dev_id":      "alice",
        "owner":       "acme",
        "repo":        "myapp",
        "branch":      "feature/login",
        "path":        "src/auth.py",
        "base_commit": "abc123",
        "patch":       "<unified diff string>",
        "author":      "Alice Smith",      // optional, falls back to dev_id
        "timestamp":   1700000000.0        // optional, falls back to now
    }

    --- branch_update ---
    Sent when the developer switches to a different branch.
    Their uncommitted patches are migrated to the new branch.
    {
        "type":           "branch_update",
        "dev_id":         "alice",
        "owner":          "acme",
        "repo":           "myapp",
        "old_branch":     "feature/login",
        "new_branch":     "feature/signup",
        "base_commit":    "abc123",
        "new_base_commit": "def456"   // optional — if the new branch has a different tip
    }

    """
    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "ok": False,
                    "error": "invalid_json",
                    "detail": "Message must be valid JSON"
                }))
                continue

            msg_type = msg.get("type")
            print(msg)
            # patch_update — developer sent a code change
            if msg_type == "patch_update":
                await handle_patch_update(websocket, msg)

            # branch_update — developer switched branches
            elif msg_type == "branch_update":
                await handle_branch_update(websocket, msg)

            #unknown message type
            else:
                await websocket.send_text(json.dumps({
                    "ok": False,
                    "error": "unknown_type",
                    "detail": f"Unknown message type: '{msg_type}'. Expected: patch_update | branch_update"
                }))

    except WebSocketDisconnect:
        print("WebSocket disconnected")

async def handle_patch_update(websocket, msg):
    try:
        file, patch = parse_update(msg)
    except KeyError as e:
        await websocket.send_text(json.dumps({
            "ok": False,
            "error": "missing_field",
            "detail": f"Required field missing: {e}"
        }))
        return
    
    from app.db.db import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await repo_manager.patch_update(db, file, patch)

    print(result)

    # publish updated snapshot to webapp clients watching this specific branch
    sub_key = f"{file.owner}/{file.repo}:{patch.branch}"
    if activity_feed.has_subscribers(sub_key):
        snapshot = repo_manager.get_active_devs(file.owner, file.repo, patch.branch)
        await activity_feed.publish(sub_key, {
            "type": "activity_snapshot",
            "repo": f"{file.owner}/{file.repo}",
            "active_devs": snapshot
        })

    if result.get("outdated"):
        response = {
            "ok": False,
            "type": "patch_update",
            "error": "outdated",
            "detail": result["details"]
        }
    elif result.get("conflict"):
        response = {
            "ok": True,
            "type": "patch_update",
            "conflict": True,
            "conflicting_dev_lines": result["conflicting_dev_lines"],
            "conflicting_branch_lines": result["conflicting_branch_lines"]
        }
    else:
        response = {
            "ok": True,
            "type": "patch_update",
            "conflict": False,
        }

    await websocket.send_text(json.dumps(response))

async def handle_branch_update(websocket, msg):
    print(f"DEBUG: Received branch_update: {msg}")
    try:
        # Extract fields first
        dev_id = msg["dev_id"]
        owner = msg["owner"]
        repo_name = msg["repo"]
        old_branch = msg["old_branch"]
        new_branch = msg["new_branch"]
        base_commit = msg["base_commit"]
        new_base_commit = msg.get("new_base_commit")
    except KeyError as e:
        print(f"DEBUG: branch_update failed - missing field: {e}")
        await websocket.send_text(json.dumps({
            "ok": False,
            "error": "missing_field",
            "detail": f"Required field missing: {e}"
        }))
        return
    
    try:
        print(f"DEBUG: Executing branch_update for {owner}/{repo_name}: {old_branch} -> {new_branch}")
        repo_manager.branch_update(
            dev_id=dev_id,
            owner=owner,
            repo_name=repo_name,
            old_branch=old_branch,
            new_branch=new_branch,
            base_commit=base_commit,
            new_base_commit=new_base_commit,
        )
        await websocket.send_text(json.dumps({
            "ok": True,
            "type": "branch_update",
        }))
        print("DEBUG: branch_update SUCCESS")
    except Exception as e:
         print(f"DEBUG: branch_update error: {e}")
         await websocket.send_text(json.dumps({
            "ok": False,
            "error": "server_error",
            "detail": f"An error occurred while updating branch: {str(e)}"
        }))

async def periodic_activity_push():
    INTERVAL = 300  # 5 minutes because patch_updates trigger immediate pushes. keeping this push as a fallback for sse connection
    while True:
        await asyncio.sleep(INTERVAL)
        try:
            for sub_key, queues in list(activity_feed.subscribers.items()):
                if not queues:
                    continue
                repo_key, branch = sub_key.rsplit(":", 1)
                owner, repo_name = repo_key.split("/", 1)
                snapshot = repo_manager.get_active_devs(owner, repo_name, branch)
                await activity_feed.publish(sub_key, {
                    "type": "activity_snapshot",
                    "repo": repo_key,
                    "branch": branch,
                    "active_devs": snapshot
                })
        except Exception as e:
            logger.error(f"periodic_activity_push error: {e}")