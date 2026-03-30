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
            .join(UserAccess, Repository.repository_id == UserAccess.c.repository_id)
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
            .join(UserAccess, Repository.repository_id == UserAccess.c.repository_id)
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

@router.get("/repos/{repo_id}/branch-health")
async def get_branch_health(repo_id: int, request: Request, branch_name: str = None):
    """
    Return two-way conflict data between a feature branch and the repo's default branch.

    Uses merge-base hunk coordinates from both compare directions so there are no false
    positives from line-shift. File contents are never fetched or stored.

    Returns:
        is_default: true if branch_name is the default branch (no panel needed)
        ahead_by, behind_by: commit distance in each direction
        base_conflicts: {filename -> [[start, end], ...]} overlapping hunk ranges
    """
    current_user: User = request.state.user

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.db.models.models import UserAccess, Repository, User as DBUser

        # Verify access and fetch repo
        result = await db.execute(
            select(Repository)
            .join(UserAccess, Repository.repository_id == UserAccess.c.repository_id)
            .where(
                UserAccess.c.user_id == current_user.user_id,
                Repository.repository_id == repo_id
            )
        )
        repo = result.scalar_one_or_none()
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found or access denied")

        default_branch = repo.repo_default_branch or "main"

        # Short-circuit for the default branch itself
        if not branch_name or branch_name == default_branch:
            return {"is_default": True}

        # Get the user's GitHub token (needed for private repos / higher rate limits)
        token_result = await db.execute(
            select(DBUser.user_github_token).where(DBUser.user_id == current_user.user_id)
        )
        token = token_result.scalar_one_or_none()

    # owner/repo extracted from "owner/repo" stored in repo_name
    parts = repo.repo_name.split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=500, detail="Invalid repo name format in database")
    owner, repo_name = parts

    from app.StateTracker import repo_manager
    try:
        result = repo_manager.github_api.get_two_way_diff(
            owner=owner,
            repo_name=repo_name,
            default_branch=default_branch,
            feature_branch=branch_name,
            token=token,
        )
    except Exception as e:
        logger.error(f"branch-health fetch failed for {owner}/{repo_name} branch={branch_name}: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch branch diff from GitHub")

    # Find uncommitted live conflicts using RepoManager's in-memory state
    uncommitted_conflicts = {}
    repo_obj = repo_manager.repos.get(repo.repo_name)
    if repo_obj:
        from collections import defaultdict
        from intervaltree import IntervalTree
        
        # 1. Gather all LIVE (uncommitted) intervals for feature_branch
        feature_live = defaultdict(IntervalTree)
        for dev_id, branches in repo_obj.dev_intervals.items():
            if dev_id == "github-commit": continue
            if branch_name in branches:
                for path, intervals in branches[branch_name].items():
                    for ival in intervals:
                        feature_live[path].addi(ival.begin, ival.end, ival.data)

        # 2. Gather ALL intervals (commits + live) for default_branch
        default_all = defaultdict(IntervalTree)
        for dev_id, branches in repo_obj.dev_intervals.items():
            if default_branch in branches:
                for path, intervals in branches[default_branch].items():
                    for ival in intervals:
                        default_all[path].addi(ival.begin, ival.end, ival.data)

        # 3. Find overlaps
        for path, f_tree in feature_live.items():
            if path in default_all:
                m_tree = default_all[path]
                overlaps = []
                for f_ival in f_tree:
                    if m_tree.overlap(f_ival.begin, f_ival.end):
                        overlaps.append([f_ival.begin, f_ival.end])
                if overlaps:
                    uncommitted_conflicts[path] = overlaps

    return {
        "is_default": False,
        "default_branch": default_branch,
        "feature_branch": branch_name,
        **result,
        "uncommitted_conflicts": uncommitted_conflicts,
    }
