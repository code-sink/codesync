import json
import logging
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from .StateTracker.RepoManager import RepoManager
from .StateTracker.FileCache import File
from .StateTracker.FileStates import PatchEvent
from .utls import parse_update
from app.routes import auth
from app.routes import user_repos
from app.routes import webhooks
from .db.db import create_all_tables
from app.middleware.auth_middleware import AuthMiddleware, get_current_user_ws

logger = logging.getLogger(__name__)
repo_manager = RepoManager()

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

app.include_router(auth.router)
app.include_router(user_repos.router)
app.include_router(webhooks.router)

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

    --- base_commit_update ---
    Sent when the developer pulls or rebases, advancing the branch tip.
    Their stored patches are re-keyed to the new base commit hash.
    {
        "type":     "base_commit_update",
        "dev_id":   "alice",
        "owner":    "acme",
        "repo":     "myapp",
        "branch":   "feature/login",
        "old_base": "abc123",
        "new_base": "def456"
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

            # patch_update — developer sent a code change
            if msg_type == "patch_update":
                await handle_patch_update(websocket, msg)

            # branch_update — developer switched branches
            elif msg_type == "branch_update":
                await handle_branch_update(websocket, msg)

            # base_commit_update — developer pulled / rebased
            elif msg_type == "base_commit_update":
                await handle_base_commit_update(websocket, msg)

            #unknown message type
            else:
                await websocket.send_text(json.dumps({
                    "ok": False,
                    "error": "unknown_type",
                    "detail": f"Unknown message type: '{msg_type}'. Expected: patch_update | branch_update | base_commit_update"
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
    
    result = repo_manager.patch_update(file, patch)

    if result.get("invalid_patch"):
        response = {
            "ok": False,
            "type": "patch_update",
            "error": "invalid_patch",
            "detail": "Patch does not apply to the given base commit"
        }
    elif result.get("conflict"):
        response = {
            "ok": True,
            "type": "patch_update",
            "conflict": True,
            "conflicting_patches": result["conflicting_patches"] # list of (patch, content with conflicts)
        }
    else:
        response = {
            "ok": True,
            "type": "patch_update",
            "conflict": False,
        }

    await websocket.send_text(json.dumps(response))

async def handle_branch_update(websocket, msg):
    try:
        repo_manager.branch_update(
            dev_id=msg["dev_id"],
            owner=msg["owner"],
            repo_name=msg["repo"],
            old_branch=msg["old_branch"],
            new_branch=msg["new_branch"],
            base_commit=msg["base_commit"],
            new_base_commit=msg.get("new_base_commit"),
        )
        await websocket.send_text(json.dumps({
            "ok": True,
            "type": "branch_update",
        }))
    except KeyError as e:
        await websocket.send_text(json.dumps({
            "ok": False,
            "error": "missing_field",
            "detail": f"Required field missing: {e}"
        }))

async def handle_base_commit_update(websocket, msg):
    try:
        repo_manager.base_commit_update(
            dev_id=msg["dev_id"],
            owner=msg["owner"],
            repo_name=msg["repo"],
            branch=msg["branch"],
            old_base=msg["old_base"],
            new_base=msg["new_base"],
        )
        await websocket.send_text(json.dumps({
            "ok": True,
            "type": "base_commit_update",
        }))
    except KeyError as e:
        await websocket.send_text(json.dumps({
            "ok": False,
            "error": "missing_field",
            "detail": f"Required field missing: {e}"
        }))