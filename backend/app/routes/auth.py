import hmac
import httpx
import os
import secrets

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.jwt import create_access_token
from app.db.db import get_db
from app.db.models.models import User
from app.middleware.auth_middleware import cookie_kwargs

load_dotenv()

CLIENT_ID    = os.getenv("CLIENT_ID")
CLIENT_SECRET= os.getenv("CLIENT_SECRET")
FRONT_URL    = os.getenv("FRONT_URL")

router = APIRouter(prefix="/auth", tags=["Authentication"])

class ExtensionAuthRequest(BaseModel):
    github_token: str

async def authenticate_github_user(github_token: str, db: AsyncSession) -> User:
    """
    Fetch the user profile from GitHub using the given token and upsert
    the user in the database.
    """
    # Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/json"},
        )
        if user_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid GitHub token")
        github_user = user_response.json()

    github_id = str(github_user["id"])

    # Upsert user
    result = await db.execute(select(User).where(User.user_github_id == github_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            user_github_id=github_id,
            user_github_token=github_token,
            user_github_login=github_user.get("login"),
            user_avatar_url=github_user.get("avatar_url"),
        )
        db.add(user)
    else:
        user.user_github_token = github_token
        user.user_github_login = github_user.get("login")
        user.user_avatar_url = github_user.get("avatar_url")

    await db.commit()
    await db.refresh(user)
    
    return user


@router.get("/github")
async def github_login():
    """Redirect to GitHub OAuth consent, setting a short-lived cookie nonce for CSRF protection."""
    nonce = secrets.token_urlsafe(32)

    params = "&".join([
        f"client_id={CLIENT_ID}",
        "scope=repo read:user user:email",
        f"state={nonce}",
        "allow_signup=true",
    ])
    redirect = RedirectResponse(url=f"https://github.com/login/oauth/authorize?{params}")

    # Store the nonce in a short-lived HttpOnly cookie.
    # On callback we compare state param == cookie to prevent Login CSRF.
    redirect.set_cookie(
        key="oauth_nonce",
        value=nonce,
        max_age=300,        # 5 minutes
        httponly=True,
        samesite="lax",
        path="/auth/github/callback",  # narrow scope
    )
    return redirect


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange the OAuth code for a GitHub token, upsert the User, and hand
    the new JWT to AuthMiddleware via request.state.new_token so the cookie
    is set in one central place.
    """
    expected_nonce = request.cookies.get("oauth_nonce")
    if not expected_nonce or not hmac.compare_digest(expected_nonce, state):
        raise HTTPException(status_code=400, detail="Invalid or expired state token.")

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": code},
        )
        token_data = token_response.json()

    if "error" in token_data:
        raise HTTPException(
            status_code=400,
            detail=f"GitHub error: {token_data.get('error_description', token_data['error'])}",
        )

    github_token = token_data["access_token"]
    user = await authenticate_github_user(github_token, db)

    request.state.new_token = create_access_token(user.user_id)

    response = RedirectResponse(url=f"{FRONT_URL}/repos")
    response.delete_cookie(key="oauth_nonce", path="/auth/github/callback")
    return response


@router.post("/extension/login")
async def extension_login(
    payload: ExtensionAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Called by the VS Code extension. Takes a valid GitHub token,
    upserts the user, and returns a JWT directly in the response body.
    """
    user = await authenticate_github_user(payload.github_token, db)
    jwt = create_access_token(user.user_id)
    return {"access_token": jwt, "token_type": "bearer"}


@router.get("/logout")
async def logout():
    response = RedirectResponse(url=FRONT_URL)
    response.set_cookie(
        key="access_token",
        value="",
        max_age=0,
        expires="Thu, 01 Jan 1970 00:00:00 GMT",
        **cookie_kwargs(),
    )
    return response