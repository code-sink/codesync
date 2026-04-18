import json
import logging
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from .StateTracker.RepoManager import RepoManager
from .StateTracker.GithubAPI import File
from .StateTracker.FileStates import PatchEvent
from .utls import parse_update
from app.routes import auth
from app.routes import user_repos
from app.routes import webhooks
from .db.db import create_all_tables
from app.middleware.auth_middleware import AuthMiddleware, get_current_user_ws

from .StateTracker import repo_manager

app = FastAPI()
app.add_middleware(AuthMiddleware)

import os
from dotenv import load_dotenv

load_dotenv()
FRONT_URL = os.getenv("FRONT_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONT_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    await create_all_tables()


app.include_router(auth.router)
app.include_router(user_repos.router)
app.include_router(webhooks.router)


@app.websocket("/developer-updates")
async def developer_updates(websocket: WebSocket, user=Depends(get_current_user_ws)):
    """
    Single persistent WebSocket connection per developer session.

    Expected message format (JSON):
    {
        "type": "patch_update" | "branch_update",
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
    {
        "type":            "branch_update",
        "dev_id":          "alice",
        "owner":           "acme",
        "repo":            "myapp",
        "old_branch":      "feature/login",
        "new_branch":      "feature/signup",
        "base_commit":     "abc123",
        "new_base_commit": "def456"   // optional
    }
    """
    await websocket.accept()

    # Track dev_id from the first message so we can clean up on disconnect.
    connected_dev_id: list[str] = [None]

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

            if msg_type == "patch_update":
                await handle_patch_update(websocket, msg, connected_dev_id)

            elif msg_type == "branch_update":
                await handle_branch_update(websocket, msg, connected_dev_id)

            else:
                await websocket.send_text(json.dumps({
                    "ok": False,
                    "error": "unknown_type",
                    "detail": (
                        f"Unknown message type: '{msg_type}'. "
                        "Expected: patch_update | branch_update"
                    )
                }))

    except WebSocketDisconnect:
        dev_id = connected_dev_id[0]
        print(f"WebSocket disconnected: {dev_id}")
        if dev_id:
            # Remove all live intervals for this dev so the tree doesn't
            # accumulate phantom entries from developers who have closed their editor.
            repo_manager.clear_all_dev_intervals(dev_id)


async def handle_patch_update(websocket: WebSocket, msg: dict, connected_dev_id: list):
    try:
        file, patch = parse_update(msg)
    except (KeyError, ValueError) as e:
        await websocket.send_text(json.dumps({
            "ok": False,
            "error": "missing_field",
            "detail": f"Required field missing: {e}"
        }))
        return

    # Remember this dev_id so disconnect handler can clean up their intervals.
    connected_dev_id[0] = patch.dev_id

    from app.db.db import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await repo_manager.patch_update(db, file, patch)

    print(result)
    await websocket.send_text(json.dumps(result))


async def handle_branch_update(websocket: WebSocket, msg: dict, connected_dev_id: list):
    print(f"DEBUG: Received branch_update: {msg}")
    try:
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

        # Remember dev_id in case this is the first message we receive from them.
        connected_dev_id[0] = dev_id

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