import logging

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import selectinload

from app.db.db import AsyncSessionLocal
from app.db.models.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["User"])


@router.get("/repos")
async def list_repos(request: Request):
    """
    Return the repos the authenticated user has access to in our database.
    """
    current_user: User = request.state.user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.db.models.models import UserAccess, Repository

        result = await db.execute(
            select(Repository)
            .join(UserAccess, Repository.repository_id == UserAccess.c.repo_id)
            .where(UserAccess.c.user_id == current_user.user_id)
        )
        repos = result.scalars().all()

    return {
        "user": {
            "github_id": current_user.user_github_id,
            "login": current_user.user_github_login,
            "avatar_url": current_user.user_avatar_url,
        },
        "repos": [
            {
                "id": repo.repository_id,
                "github_id": repo.repo_github_id,
                "name": repo.repo_name,
                "description": repo.repo_description,
                "html_url": repo.repo_html_url,
                "language": repo.repo_language,
                "default_branch": repo.repo_default_branch,
                "private": repo.repository_is_private,
                "updated_at": repo.repository_updated_at.isoformat() if repo.repository_updated_at else None,
            }
            for repo in repos
        ],
    }

@router.get("/repos/{repo_id}")
async def get_repo_details(repo_id: int, request: Request, branch_id: int = None):
    """
    Return the details of a specific repository, its branches, and the files
    for the selected branch (or the default branch if none is provided).
    Ensures the user has access.
    """
    current_user: User = request.state.user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.db.models.models import UserAccess, Repository, Branch, File

        # Verify access and fetch repo
        result = await db.execute(
            select(Repository)
            .join(UserAccess, Repository.repository_id == UserAccess.c.repo_id)
            .where(
                UserAccess.c.user_id == current_user.user_id,
                Repository.repository_id == repo_id
            )
            .options(selectinload(Repository.branches))
        )
        repo = result.scalar_one_or_none()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found or access denied")

        # --- Lazy initialization ---
        # If the repo has no branches yet, we haven't fully populated it.
        # Trigger full initialization now (blocks until done so the response is complete).
        branch_ids_check = await db.execute(
            select(Branch.branch_id).where(Branch.repository_id == repo.repository_id).limit(1)
        )
        if branch_ids_check.scalar_one_or_none() is None:
            # Need the user's GitHub token to call the API
            from sqlalchemy import select as sa_select
            token_result = await db.execute(
                sa_select(User.user_github_token).where(User.user_id == current_user.user_id)
            )
            token = token_result.scalar_one_or_none()
            if token:
                from app.routes.webhooks import _ensure_repo_initialized
                initialized = await _ensure_repo_initialized(repo, token, db)
                if initialized:
                    await db.commit()
                    # Reload repo with fresh branch data
                    result2 = await db.execute(
                        select(Repository)
                        .where(Repository.repository_id == repo_id)
                        .options(selectinload(Repository.branches))
                    )
                    repo = result2.scalar_one_or_none() or repo
            else:
                logger.warning(f"Cannot lazy-init repo {repo_id}: no token for user {current_user.user_id}")

        # Determine which branch to load files for
        selected_branch = None
        if branch_id:
            selected_branch = next((b for b in repo.branches if b.branch_id == branch_id), None)
        
        # Fallback to default branch if possible
        if not selected_branch and repo.repo_default_branch:
            selected_branch = next((b for b in repo.branches if b.branch_name == repo.repo_default_branch), None)
        
        # Ultimate fallback to the first branch if default doesn't match
        if not selected_branch and repo.branches:
            selected_branch = repo.branches[0]

        files = []
        if selected_branch:
            file_result = await db.execute(
                select(File)
                .where(File.branch_id == selected_branch.branch_id)
                .order_by(File.file_path)
            )
            files = file_result.scalars().all()

    return {
        "repo": {
            "id": repo.repository_id,
            "name": repo.repo_name,
            "description": repo.repo_description,
            "html_url": repo.repo_html_url,
            "language": repo.repo_language,
            "default_branch": repo.repo_default_branch,
            "private": repo.repository_is_private,
        },
        "branches": [
            {
                "id": b.branch_id,
                "name": b.branch_name,
                "created_at": b.branch_created_at.isoformat() if b.branch_created_at else None,
                "updated_at": b.branch_updated_at.isoformat() if b.branch_updated_at else None,
            }
            for b in repo.branches
        ],
        "active_branch": {
            "id": selected_branch.branch_id if selected_branch else None,
            "name": selected_branch.branch_name if selected_branch else None,
            "created_at": selected_branch.branch_created_at.isoformat() if selected_branch and selected_branch.branch_created_at else None,
            "updated_at": selected_branch.branch_updated_at.isoformat() if selected_branch and selected_branch.branch_updated_at else None,
        },
        "files": [f.file_path for f in files]
    }
