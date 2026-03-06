import os
from time import time
from dataclasses import dataclass
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request, HTTPException, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from dotenv import load_dotenv

from app.db.db import AsyncSessionLocal, get_db
from app.db.models.models import User
from app.auth.jwt import decode_access_token

load_dotenv()
IS_DEV = os.getenv("IS_DEV", "true").lower() == "true"

# Public endpoints that do not need authentication
_PUBLIC_PATHS = {
    "/auth/github",
    "/auth/github/callback",
    "/auth/github/app-callback", 
    "/auth/logout",
    "/webhooks/github",
    "/docs",
    "/openapi.json",
}


def cookie_kwargs() -> dict:
    """
    Return the cookie attributes appropriate for the current environment.

    Dev  (IS_DEV=true)  – HTTP-only localhost, SameSite=Lax, not Secure.
    Prod (IS_DEV=false) – HTTPS, HttpOnly, SameSite=None, Secure.
    """
    if IS_DEV:
        return dict(httponly=False, samesite="lax", secure=False, path="/")
    return dict(httponly=True, samesite="none", secure=True, path="/")


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Centralized authentication middleware.

    For every non-public request:
      1. Extract the JWT from the 'access_token' cookie or Authorization header.
      2. Decode and verify the JWT.
      3. Load the matching User from the database.
      4. Attach the user to `request.state.user`.

    Additionally, if a route stores a new JWT in `request.state.new_token`
    (e.g. the GitHub callback after a successful login), the middleware will
    attach that token as a Set-Cookie header on the outgoing response.
    This keeps all cookie logic in one place.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always let CORS preflight through — browsers send OPTIONS without cookies
        if request.method == "OPTIONS":
            return await call_next(request)

        is_public = path in _PUBLIC_PATHS or any(
            path.startswith(p) for p in ("/docs", "/openapi")
        )

        if not is_public:
            # token from cookie or Authorization header
            access_token = request.cookies.get("access_token")
            auth_header = request.headers.get("Authorization", "")
            if not access_token and auth_header.startswith("Bearer "):
                access_token = auth_header.split(" ", 1)[1]

            print(f"\n--- Auth Middleware [{request.method} {path}] ---")
            print(f"  Cookie token : {'present (' + access_token[:12] + '...)' if access_token else 'None'}")

            if not access_token:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated: no access_token cookie or Authorization header"},
                )

            # validate JWT
            try:
                payload = decode_access_token(access_token)
                user_id = int(payload["sub"])
            except Exception as exc:
                print(f"  JWT error    : {exc}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                )

            # load user from DB
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.user_id == user_id))
                user = result.scalar_one_or_none()

            if user is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "User not found"},
                )

            print(f"  User         : id={user.user_id}")
            # attach user to request state so route handlers can read it
            request.state.user = user

        # call the actual route handler
        response = await call_next(request)

        # if the route stored a new JWT (e.g. after OAuth callback login),
        # attach it as a Set-Cookie header here so all cookie logic lives in one place
        new_token = getattr(request.state, "new_token", None)
        if new_token:
            response.set_cookie(
                key="access_token",
                value=new_token,
                max_age=60 * 60 * 24 * 7,  # 7 days
                **cookie_kwargs(),
            )

        return response


# WebSockets are not handled by HTTP middleware, so we still need a small
# dependency function for the WebSocket endpoint.

async def get_current_user_ws(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency for WebSocket endpoints that replicates the middleware logic.
    """
    access_token = websocket.cookies.get("access_token")
    if not access_token:
        access_token = websocket.query_params.get("token")

    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(access_token)
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
