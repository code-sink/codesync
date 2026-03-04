from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
import os
import secrets
import json
import requests

# Load variables from .env file
load_dotenv()

# Access and set to variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

router = APIRouter(
    prefix="/auth",          # All routes start with /auth
    tags=["Authentication"]  # Tag for documentation grouping
)

# In-memory store for CSRF state tokens
_pending_states: set[str] = set()

@router.get("/github")
async def github_login():
    # Redirect the user to GitHub's OAuth authorization page
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": "http://localhost:8000/auth/github/callback",
        "scope": "repo read:user user:email",   # public + private repos, files, profile
        "state": state,
        "allow_signup": "true",
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    github_url = f"https://github.com/login/oauth/authorize?{query_string}"
    return RedirectResponse(url=github_url)

@router.get("/github/callback")
async def github_callback(code, state):
    # Handle the GitHub OAuth callback

    #Validate state token to prevent CSRF
    if state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state token.")
    _pending_states.discard(state)

    # Exchange the authorization code for an access token
    response = await requests.post(url="https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": code})
    token_data = response.json()

    if "error" in token_data:
        raise HTTPException(
            status_code=400,
            detail=f"GitHub token exchange failed: {token_data.get('error_description', token_data['error'])}",
        )
    
    token = token_data["access_token"]
    token_type = token_data.get("token_type", "bearer")

    return {"token": token, "token_type": token_type}