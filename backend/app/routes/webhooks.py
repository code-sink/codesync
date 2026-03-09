import asyncio
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.db import AsyncSessionLocal
from app.db.models.models import User, Repository, UserAccess, Branch, File

load_dotenv()

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _verify_signature(payload: bytes, signature: str) -> bool:
    """Verify that the payload was sent by GitHub using the webhook secret."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not set — skipping signature verification")
        return True
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _get_sender_token(db: AsyncSession, sender: dict) -> str | None:
    """
    Look up the sender's stored GitHub OAuth token from our database.
    The sender is the person who triggered the webhook (installed the app, etc).
    Since they came from our frontend, they should have a stored token.
    """
    github_id = str(sender.get("id", ""))
    if not github_id:
        return None
    result = await db.execute(select(User).where(User.user_github_id == github_id))
    user = result.scalar_one_or_none()
    if user and user.user_github_token:
        return user.user_github_token
    return None


async def _upsert_user_by_github_id(db: AsyncSession, github_id: str, login: str = None, avatar_url: str = None) -> User:
    """Find or create a User by their github_id. Returns the User object."""
    result = await db.execute(select(User).where(User.user_github_id == github_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            user_github_id=github_id,
            user_github_login=login,
            user_avatar_url=avatar_url,
        )
        db.add(user)
        await db.flush()  # get user_id assigned
    else:
        if login:
            user.user_github_login = login
        if avatar_url:
            user.user_avatar_url = avatar_url
    return user


async def _grant_access(db: AsyncSession, user_id: int, repo_id: int):
    """Insert a UserAccess row if it doesn't already exist."""
    existing = await db.execute(
        select(UserAccess)
        .where(UserAccess.c.user_id == user_id, UserAccess.c.repo_id == repo_id)
    )
    if existing.first() is None:
        await db.execute(UserAccess.insert().values(user_id=user_id, repo_id=repo_id))


async def _onboard_single_repo(repo_data: dict, installation_id: int, token: str, grant_user_id: int | None = None):
    """Upsert a single repo's basic metadata and grant access.
    Full initialization (branches, files, collaborators) is done lazily on first access.
    """
    async with AsyncSessionLocal() as db:
        repo = await _upsert_repo(db, repo_data, installation_id, token)
        if grant_user_id is not None:
            await _grant_access(db, grant_user_id, repo.repository_id)
        await db.commit()


async def _ensure_repo_initialized(repo: Repository, token: str, db: AsyncSession) -> bool:
    """Check if the repo has been fully initialized (has branches). If not, run full
    population now. Returns True if just initialized, False if already was.
    Uses presence of Branch records as a proxy for initialization status.
    """
    branch_check = await db.execute(
        select(Branch.branch_id).where(Branch.repository_id == repo.repository_id).limit(1)
    )
    if branch_check.scalar_one_or_none() is not None:
        return False  # already initialized

    logger.info(f"Lazy-initializing repo {repo.repo_name}...")
    await _sync_collaborators(db, repo, token)
    await _populate_repo_contents(token, repo.repo_name, repo, db)
    await db.flush()
    return True


async def _populate_repo_contents(token: str, repo_full_name: str, repo: Repository, db: AsyncSession):
    """
    Fetch all branches for a repo, then for each branch fetch the file tree,
    and populate Branch + File tables.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient() as client:
        # Fetch branches

        branches_resp = await client.get(
            f"https://api.github.com/repos/{repo_full_name}/branches",
            headers=headers,
            params={"per_page": 100},
        )
        if branches_resp.status_code != 200:
            logger.debug(f"Failed to fetch branches for {repo_full_name}: {branches_resp.status_code}")
            return

        for branch_data in branches_resp.json():
            branch_name = branch_data["name"]

            # Guard against race condition: if this repo was deleted by a concurrent
            # removal webhook (e.g. admin switched from "all repos" to specific repos)
            # while we're still populating, stop immediately.
            repo_check = await db.execute(
                select(Repository.repository_id).where(
                    Repository.repository_id == repo.repository_id
                )
            )
            if repo_check.scalar_one_or_none() is None:
                logger.warning(
                    f"Repo {repo_full_name} was deleted mid-populate, aborting."
                )
                return

            # Check if branch already exists
            result = await db.execute(
                select(Branch).where(
                    Branch.repository_id == repo.repository_id,
                    Branch.branch_name == branch_name,
                )
            )
            branch = result.scalar_one_or_none()

            # Fetch the actual commit for precise branch timestamps and to get the branch SHA
            commit_resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/commits/{branch_name}",
                headers=headers,
            )
            
            branch_sha = ""
            branch_time = datetime.now(timezone.utc)
            if commit_resp.status_code == 200:
                commit_data = commit_resp.json()
                branch_sha = commit_data.get("sha", "")
                date_str = commit_data.get("commit", {}).get("author", {}).get("date", "")
                if date_str:
                    try:
                        branch_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
            
            if branch is None:
                branch = Branch(
                    branch_name=branch_name,
                    branch_created_at=branch_time,
                    branch_updated_at=branch_time,
                    repository_id=repo.repository_id,
                )
                db.add(branch)
                await db.flush()
            else:
                branch.branch_updated_at = branch_time

            # Fetch the file tree for this branch
            tree_resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/git/trees/{branch_name}",
                headers=headers,
                params={"recursive": "true"},
            )
            if tree_resp.status_code != 200:
                logger.debug(f"Failed to fetch tree for {repo_full_name}:{branch_name}")
                continue

            tree = tree_resp.json().get("tree", [])
            for item in tree:
                if item["type"] != "blob":
                    continue  # skip directories

                file_path = item["path"]
                # Check if file already exists for this branch
                file_result = await db.execute(
                    select(File).where(
                        File.branch_id == branch.branch_id,
                        File.file_path == file_path,
                    )
                )
                if file_result.scalar_one_or_none() is None:
                    db.add(File(
                        file_path=file_path, 
                        branch_id=branch.branch_id, 
                        file_latest_commit=branch_sha
                    ))

    await db.flush()


@router.post("/github")
async def github_webhook(request: Request):
    """
    Handle GitHub App webhook events.

    Supported events:
    - installation (created): upsert repo + collaborators, populate files
    - installation_repositories (added/removed): handle repo changes
    - member (removed): revoke UserAccess
    """
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")

    if not _verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("x-github-event", "")
    payload = await request.json()
    action = payload.get("action", "")

    logger.info(f"Webhook received: event={event} action={action}")

    if event == "installation" and action == "created":
        await _handle_installation_created(payload)

    elif event == "installation" and action == "deleted":
        await _handle_installation_deleted(payload)

    elif event == "installation_repositories":
        if action == "added":
            await _handle_repos_added(payload)
        elif action == "removed":
            await _handle_repos_removed(payload)

    elif event == "member" and action == "removed":
        await _handle_member_removed(payload)

    elif event == "push":
        await _handle_push(payload)

    return {"status": "ok"}


async def _handle_installation_created(payload: dict):
    """
    Fires when a user installs the code-sink App on one or more repositories.

    The sender is the person who clicked Install on GitHub. Their stored OAuth
    token is used to call GitHub APIs (list collaborators, file tree, etc.).

    IMPORTANT: The sender must have previously logged into CodeSync so their
    token is stored in our DB. If they haven't, we log an error and skip.
    The user should log in to CodeSync FIRST, then install the GitHub App.
    """
    installation_id = payload["installation"]["id"]
    repos = payload.get("repositories", [])
    sender = payload.get("sender", {})
    sender_login = sender.get("login", "unknown")

    logger.info(
        f"Installation created: id={installation_id} sender={sender_login} "
        f"repos={[r.get('full_name') for r in repos]}"
    )

    async with AsyncSessionLocal() as db:
        # We need the sender's stored OAuth token to call GitHub APIs.
        # The sender must have logged into CodeSync first.
        token = await _get_sender_token(db, sender)
        if not token:
            logger.error(
                f"Installation webhook from '{sender_login}' but this user has not "
                f"logged into CodeSync yet. They must log in to CodeSync FIRST, "
                f"then install the GitHub App. Skipping installation processing."
            )
            return

        sender_user = await _upsert_user_by_github_id(
            db, str(sender["id"]), sender.get("login"), sender.get("avatar_url")
        )
        sender_user_id = sender_user.user_id
        await db.commit()

    # Basic metadata upsert only — full initialization happens lazily on first access
    for repo_data in repos:
        await _onboard_single_repo(repo_data, installation_id, token, grant_user_id=sender_user_id)

    logger.info(f"Installation {installation_id}: {len(repos)} repo(s) registered for {sender_login} (lazy init)")

    # Reconcile DB with GitHub's authoritative repo list for this installation
    await _reconcile_installation(installation_id, token)


async def _handle_repos_added(payload: dict):
    """Repos were added to an existing installation."""
    installation_id = payload["installation"]["id"]
    repos = payload.get("repositories_added", [])
    sender = payload.get("sender", {})

    async with AsyncSessionLocal() as db:
        token = await _get_sender_token(db, sender)
        if not token:
            logger.error(f"No stored token for sender {sender.get('id')} — cannot process repos_added")
            return

        sender_user = await _upsert_user_by_github_id(
            db, str(sender["id"]), sender.get("login"), sender.get("avatar_url")
        )
        sender_user_id = sender_user.user_id
        await db.commit()

    # Basic metadata upsert only — full initialization happens lazily on first access
    for repo_data in repos:
        await _onboard_single_repo(repo_data, installation_id, token, grant_user_id=sender_user_id)

    # Reconcile DB with GitHub's authoritative repo list for this installation
    await _reconcile_installation(installation_id, token)


async def _reconcile_installation(installation_id: int, token: str):
    """
    Query GitHub for the authoritative list of repos this installation
    currently has access to, then sync our DB:
      - delete repos in DB that GitHub no longer includes
      - add repos that GitHub has but aren't in our DB yet

    Called after every installation-related event so the DB stays in sync
    regardless of race conditions or out-of-order webhook delivery.
    """
    from sqlalchemy import delete as sa_delete
    from app.db.models.models import Branch, File, Edit

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # Fetch the real repo list from GitHub
    github_repo_ids: set[str] = set()
    github_repos: list[dict] = []
    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            resp = await client.get(
                f"https://api.github.com/user/installations/{installation_id}/repositories",
                headers=headers,
                params={"per_page": 100, "page": page},
            )
            if resp.status_code != 200:
                logger.warning(
                    f"Reconcile: failed to fetch repos for installation {installation_id}: "
                    f"{resp.status_code} — skipping reconciliation"
                )
                return
            data = resp.json()
            batch = data.get("repositories", [])
            if not batch:
                break
            for r in batch:
                github_repo_ids.add(str(r["id"]))
                github_repos.append(r)
            page += 1

    logger.info(
        f"Reconcile installation {installation_id}: "
        f"GitHub reports {len(github_repo_ids)} repo(s)"
    )

    async with AsyncSessionLocal() as db:
        # Find repos in our DB for this installation
        db_result = await db.execute(
            select(Repository).where(Repository.installation_id == installation_id)
        )
        db_repos = db_result.scalars().all()
        db_repo_ids = {r.repo_github_id for r in db_repos}

        # --- Delete repos in DB that GitHub no longer includes ---
        stale_ids = db_repo_ids - github_repo_ids
        for repo in db_repos:
            if repo.repo_github_id not in stale_ids:
                continue
            logger.info(f"Reconcile: removing stale repo {repo.repo_name}")
            await db.execute(UserAccess.delete().where(UserAccess.c.repo_id == repo.repository_id))
            branch_res = await db.execute(
                select(Branch.branch_id).where(Branch.repository_id == repo.repository_id)
            )
            branch_ids = branch_res.scalars().all()
            if branch_ids:
                file_res = await db.execute(
                    select(File.file_id).where(File.branch_id.in_(branch_ids))
                )
                file_ids = file_res.scalars().all()
                if file_ids:
                    await db.execute(sa_delete(Edit).where(Edit.file_id.in_(file_ids)))
                await db.execute(sa_delete(File).where(File.branch_id.in_(branch_ids)))
                await db.execute(sa_delete(Branch).where(Branch.repository_id == repo.repository_id))
            await db.execute(sa_delete(Repository).where(Repository.repository_id == repo.repository_id))

        await db.commit()

    # --- Add repos GitHub has that aren't in our DB ---
    new_repo_ids = github_repo_ids - db_repo_ids
    if new_repo_ids:
        new_repos = [r for r in github_repos if str(r["id"]) in new_repo_ids]
        logger.info(f"Reconcile: adding {len(new_repos)} new repo(s)")
        async with AsyncSessionLocal() as db:
            for repo_data in new_repos:
                repo = await _upsert_repo(db, repo_data, installation_id, token)
                await _sync_collaborators(db, repo, token)
                await _populate_repo_contents(token, repo.repo_name, repo, db)
            await db.commit()


async def _handle_installation_deleted(payload: dict):
    """The entire GitHub App installation was removed — clean up all repos."""
    repos = payload.get("repositories", [])
    installation_id = payload.get("installation", {}).get("id")
    logger.info(f"Installation {installation_id} deleted — removing {len(repos)} repo(s)")

    from sqlalchemy import delete as sa_delete
    from app.db.models.models import Branch, File, Edit

    async with AsyncSessionLocal() as db:
        for repo_data in repos:
            github_id = str(repo_data["id"])
            result = await db.execute(
                select(Repository).where(Repository.repo_github_id == github_id)
            )
            repo = result.scalar_one_or_none()
            if not repo:
                continue

            await db.execute(UserAccess.delete().where(UserAccess.c.repo_id == repo.repository_id))

            branch_res = await db.execute(
                select(Branch.branch_id).where(Branch.repository_id == repo.repository_id)
            )
            branch_ids = branch_res.scalars().all()

            if branch_ids:
                file_res = await db.execute(
                    select(File.file_id).where(File.branch_id.in_(branch_ids))
                )
                file_ids = file_res.scalars().all()
                if file_ids:
                    await db.execute(sa_delete(Edit).where(Edit.file_id.in_(file_ids)))
                await db.execute(sa_delete(File).where(File.branch_id.in_(branch_ids)))
                await db.execute(sa_delete(Branch).where(Branch.repository_id == repo.repository_id))

            await db.execute(sa_delete(Repository).where(Repository.repository_id == repo.repository_id))
            logger.info(f"Fully deleted repo {repo_data.get('full_name')} (app uninstalled)")
        await db.commit()


async def _handle_repos_removed(payload: dict):
    """Repos were removed from an installation."""
    repos = payload.get("repositories_removed", [])
    
    from sqlalchemy import delete as sa_delete
    from app.db.models.models import Branch, File, Edit

    async with AsyncSessionLocal() as db:
        for repo_data in repos:
            github_id = str(repo_data["id"])
            result = await db.execute(
                select(Repository).where(Repository.repo_github_id == github_id)
            )
            repo = result.scalar_one_or_none()
            if repo:
                # Remove all access entries for this repo
                await db.execute(
                    UserAccess.delete().where(UserAccess.c.repo_id == repo.repository_id)
                )
                
                # Find all branches for this repo
                branch_res = await db.execute(
                    select(Branch.branch_id).where(Branch.repository_id == repo.repository_id)
                )
                branch_ids = branch_res.scalars().all()
                
                if branch_ids:
                    # Find all files for these branches
                    file_res = await db.execute(
                        select(File.file_id).where(File.branch_id.in_(branch_ids))
                    )
                    file_ids = file_res.scalars().all()
                    
                    if file_ids:
                        # 1. Delete all Edits
                        await db.execute(
                            sa_delete(Edit).where(Edit.file_id.in_(file_ids))
                        )
                    
                    # 2. Delete all Files
                    await db.execute(
                        sa_delete(File).where(File.branch_id.in_(branch_ids))
                    )
                    
                    # 3. Delete all Branches
                    await db.execute(
                        sa_delete(Branch).where(Branch.repository_id == repo.repository_id)
                    )
                
                # 4. Finally, delete the Repository itself
                await db.execute(
                    sa_delete(Repository).where(Repository.repository_id == repo.repository_id)
                )
                logger.info(f"Fully deleted repository {repo_data.get('full_name')} from CodeSync")
        await db.commit()

    # Reconcile DB with GitHub's authoritative repo list for this installation
    installation_id = payload.get("installation", {}).get("id")
    if installation_id:
        async with AsyncSessionLocal() as db:
            # Find a token for any user with access to repos under this installation
            token_result = await db.execute(
                select(User)
                .join(UserAccess, User.user_id == UserAccess.c.user_id)
                .join(Repository, Repository.repository_id == UserAccess.c.repo_id)
                .where(
                    Repository.installation_id == installation_id,
                    User.user_github_token.isnot(None),
                )
                .limit(1)
            )
            user = token_result.scalar_one_or_none()
        if user:
            await _reconcile_installation(installation_id, user.user_github_token)
        else:
            logger.warning(f"Reconcile skipped for installation {installation_id}: no token available")


async def _handle_member_removed(payload: dict):
    """A collaborator was removed from a repository on GitHub."""
    member = payload.get("member", {})
    repo_data = payload.get("repository", {})

    github_user_id = str(member["id"])
    repo_github_id = str(repo_data["id"])

    async with AsyncSessionLocal() as db:
        user_result = await db.execute(
            select(User).where(User.user_github_id == github_user_id)
        )
        user = user_result.scalar_one_or_none()

        repo_result = await db.execute(
            select(Repository).where(Repository.repo_github_id == repo_github_id)
        )
        repo = repo_result.scalar_one_or_none()

        if user and repo:
            await db.execute(
                UserAccess.delete().where(
                    UserAccess.c.user_id == user.user_id,
                    UserAccess.c.repo_id == repo.repository_id,
                )
            )
            logger.info(f"Removed access for user {github_user_id} from repo {repo_github_id}")

        await db.commit()


async def _upsert_repo(db: AsyncSession, repo_data: dict, installation_id: int, token: str) -> Repository:
    """
    Upsert a repository by repo_github_id. If two admins add the same repo,
    the second one just updates the existing row.
    """
    github_id = str(repo_data["id"])
    full_name = repo_data.get("full_name", repo_data.get("name", ""))

    # Fetch full repo details from GitHub API for metadata
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{full_name}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if resp.status_code == 200:
            details = resp.json()
        else:
            details = {}

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(Repository)
        .values(
            repo_github_id=github_id,
            repo_name=full_name,
            repo_description=details.get("description"),
            repo_html_url=details.get("html_url"),
            repo_language=details.get("language"),
            repo_default_branch=details.get("default_branch"),
            repository_is_private=details.get("private", repo_data.get("private", False)),
            repository_updated_at=now,
            installation_id=installation_id,
        )
        .on_conflict_do_update(
            index_elements=["repo_github_id"],
            set_={
                "repo_name": full_name,
                "repo_description": details.get("description"),
                "repo_html_url": details.get("html_url"),
                "repo_language": details.get("language"),
                "repo_default_branch": details.get("default_branch"),
                "repository_is_private": details.get("private", repo_data.get("private", False)),
                "repository_updated_at": now,
                "installation_id": installation_id,
            },
        )
        .returning(Repository)
    )
    result = await db.execute(stmt)
    repo = result.scalar_one()
    return repo


async def _sync_collaborators(db: AsyncSession, repo: Repository, token: str):
    """
    Fetch all collaborators with push access from GitHub and grant them
    UserAccess in our database. Creates User rows for people who don't
    have a CodeSync account yet (by github_id).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient() as client:
        page = 1
        while True:
            resp = await client.get(
                f"https://api.github.com/repos/{repo.repo_name}/collaborators",
                headers=headers,
                params={"per_page": 100, "page": page, "affiliation": "all"},
            )
            if resp.status_code != 200:
                logger.debug(f"Failed to fetch collaborators for {repo.repo_name}: {resp.status_code}")
                break

            collaborators = resp.json()
            if not collaborators:
                break

            for collab in collaborators:
                permissions = collab.get("permissions", {})
                # Only grant access to collaborators with push (write) or admin rights
                if not permissions.get("push", False) and not permissions.get("admin", False):
                    continue

                user = await _upsert_user_by_github_id(
                    db,
                    str(collab["id"]),
                    collab.get("login"),
                    collab.get("avatar_url"),
                )
                await _grant_access(db, user.user_id, repo.repository_id)

            page += 1


async def _handle_push(payload: dict):
    """
    Handle a push event from GitHub.
    Updates the file list for the pushed branch:
      - Inserts new files
      - Deletes files that were removed in the push
    Uses the pusher's stored OAuth token for GitHub API calls.
    """
    repo_data = payload.get("repository", {})
    repo_github_id = str(repo_data.get("id", ""))
    repo_full_name = repo_data.get("full_name", "")
    ref = payload.get("ref", "")  # e.g. "refs/heads/main"
    pusher_login = payload.get("pusher", {}).get("name", "")

    if not ref.startswith("refs/heads/"):
        logger.info(f"Push event for non-branch ref {ref}, skipping")
        return

    branch_name = ref[len("refs/heads/"):]
    logger.info(f"Push event: {repo_full_name} branch={branch_name} pusher={pusher_login}")

    async with AsyncSessionLocal() as db:
        # Find the repo in our DB
        result = await db.execute(
            select(Repository).where(Repository.repo_github_id == repo_github_id)
        )
        repo = result.scalar_one_or_none()
        if repo is None:
            logger.warning(f"Push event for unknown repo github_id={repo_github_id}, ignoring")
            return

        # Get a token — try the pusher first, then fall back to any stored user token for this repo
        token = None
        if pusher_login:
            login_result = await db.execute(
                select(User).where(User.user_github_login == pusher_login)
            )
            pusher_user = login_result.scalar_one_or_none()
            if pusher_user and pusher_user.user_github_token:
                token = pusher_user.user_github_token

        if not token:
            # Fall back: any user who has access to this repo and has a stored token
            access_result = await db.execute(
                select(User)
                .join(UserAccess, User.user_id == UserAccess.c.user_id)
                .where(UserAccess.c.repo_id == repo.repository_id, User.user_github_token.isnot(None))
                .limit(1)
            )
            fallback_user = access_result.scalar_one_or_none()
            if fallback_user:
                token = fallback_user.user_github_token

        if not token:
            logger.error(f"No usable token found for push to {repo_full_name}, skipping file sync")
            return

        # Extract branch timestamp from the head_commit if available
        head_commit = payload.get("head_commit", {})
        now = datetime.now(timezone.utc)
        
        # Try parsing the head_commit timestamp
        commit_timestamp = head_commit.get("timestamp")
        if commit_timestamp:
            try:
                now = datetime.fromisoformat(commit_timestamp.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Upsert the branch
        branch_result = await db.execute(
            select(Branch).where(
                Branch.repository_id == repo.repository_id,
                Branch.branch_name == branch_name,
            )
        )
        branch = branch_result.scalar_one_or_none()
        
        if branch is None:
            branch = Branch(
                branch_name=branch_name,
                branch_created_at=now,
                branch_updated_at=now,
                repository_id=repo.repository_id,
            )
            db.add(branch)
            await db.flush()
        else:
            branch.branch_updated_at = now

        # Map newly added/modified files from commits to their exact commit sha
        file_sha_map = {}
        commits = payload.get("commits", [])
        for commit in commits:
            commit_id = commit.get("id")
            if not commit_id:
                continue
            
            for file_path in commit.get("added", []):
                file_sha_map[file_path] = commit_id
                
            for file_path in commit.get("modified", []):
                file_sha_map[file_path] = commit_id

        # Fetch the full file tree for this branch from GitHub
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient() as client:
            tree_resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/git/trees/{branch_name}",
                headers=headers,
                params={"recursive": "true"},
            )

        if tree_resp.status_code != 200:
            logger.error(f"Failed to fetch tree for {repo_full_name}:{branch_name}: {tree_resp.status_code}")
            await db.commit()
            return

        # Build the set of file paths that should exist after this push
        current_paths = {
            item["path"]
            for item in tree_resp.json().get("tree", [])
            if item["type"] == "blob"
        }

        # Load existing files for this branch
        existing_result = await db.execute(
            select(File).where(File.branch_id == branch.branch_id)
        )
        existing_files = existing_result.scalars().all()
        existing_paths = {f.file_path for f in existing_files}

        # Insert new files
        new_paths = current_paths - existing_paths
        for path in new_paths:
            db.add(File(
                file_path=path, 
                branch_id=branch.branch_id,
                file_latest_commit=file_sha_map.get(path, head_commit.get("id", ""))
            ))

        # Update existing files that were modified with their new commit sha
        modified_paths = current_paths.intersection(existing_paths)
        for existing_file in existing_files:
            if existing_file.file_path in modified_paths and existing_file.file_path in file_sha_map:
                existing_file.file_latest_commit = file_sha_map[existing_file.file_path]

        # Delete removed files
        removed_paths = existing_paths - current_paths
        if removed_paths:
            from sqlalchemy import delete as sa_delete
            await db.execute(
                sa_delete(File).where(
                    File.branch_id == branch.branch_id,
                    File.file_path.in_(removed_paths),
                )
            )

        await db.commit()
        logger.info(
            f"Push sync complete for {repo_full_name}/{branch_name}: "
            f"+{len(new_paths)} files, -{len(removed_paths)} files"
        )
