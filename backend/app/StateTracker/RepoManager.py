import time
import json
import datetime
from sqlalchemy import select, delete
from app.db.models.models import Edit, File as DBFile, Branch as DBBranch, Repository as DBRepo, User as DBUser
from .FileStates import PatchEvent
from .GithubAPI import GithubAPI, File
from collections import defaultdict
from intervaltree import IntervalTree, Interval


class Repo:
    def __init__(self):
        # file_path -> IntervalTree of [line_start, line_end) -> PatchEvent
        #
        # IMPORTANT INVARIANT: This tree contains ONLY live (uncommitted) developer edits.
        # All intervals are stored in HEAD-relative line coordinates, exactly as produced
        # by the client's `git diff HEAD` (diffWithHEAD). There are NO synthetic entries
        # representing committed branch diffs — those are stored separately in
        # GithubAPI.branch_diffs and queried directly when needed.
        #
        # This invariant guarantees that any two intervals in the same tree for the same
        # branch are always in the same coordinate space and can be compared safely.
        self.files = defaultdict(IntervalTree)
        self.default_branch = None
        # dev_id -> branch -> file_path -> set of Interval objects
        self.dev_intervals = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        
        self.last_activity = time.time()
        self.is_dirty = False
        self.is_loaded_from_db = False

    def clear_dev_branch(self, dev_id: str, branch_name: str):
        """Remove all live intervals for a dev on a specific branch from the shared trees."""
        for file_path, intervals in list(self.dev_intervals[dev_id][branch_name].items()):
            for interval_obj in list(intervals):
                self.files[file_path].discard(interval_obj)
        self.dev_intervals[dev_id][branch_name].clear()


class RepoManager:

    def __init__(self):
        self.repos = defaultdict(Repo)
        self.github_api = GithubAPI()

    async def get_inactive_dirty_repos(self, threshold_seconds=300):
        """Returns a list of repo_names that haven't been touched in threshold_seconds and are dirty."""
        now = time.time()
        inactive = []
        for repo_name, repo_obj in self.repos.items():
            if repo_obj.is_dirty and (now - repo_obj.last_activity) >= threshold_seconds:
                inactive.append(repo_name)
        return inactive

    async def _load_repo_from_db(self, db, repo_name: str):
        repo_obj = self.repos[repo_name]
        owner, repo_str = repo_name.split("/", 1)

        stmt = (
            select(Edit, DBFile, DBBranch, DBUser)
            .join(DBFile, Edit.file_id == DBFile.file_id)
            .join(DBBranch, DBFile.branch_id == DBBranch.branch_id)
            .join(DBRepo, DBBranch.repository_id == DBRepo.repository_id)
            .join(DBUser, Edit.user_id == DBUser.user_id)
            .where(DBRepo.repo_name == repo_name)
        )
        
        result = await db.execute(stmt)
        rows = result.all()

        for edit, db_file, db_branch, db_user in rows:
            if edit.edit_base_commit != db_file.file_latest_commit:
                continue

            try:
                touched_ranges = json.loads(edit.edit_ranges)
            except Exception:
                touched_ranges = []

            patch_timestamp = edit.edit_timestamp.timestamp() if edit.edit_timestamp else time.time()
            patch = PatchEvent(
                dev_id=db_user.user_github_id,
                base_commit=edit.edit_base_commit,
                branch=db_branch.branch_name,
                timestamp=patch_timestamp,
                patch_text=edit.edit_patch,
                author=db_user.user_github_login or db_user.user_github_id,
                touched_ranges=tuple(tuple(r) for r in touched_ranges)
            )

            tree = repo_obj.files[db_file.file_path]
            for start, end in patch.touched_ranges:
                new_interval = Interval(start, end + 1, patch)
                tree.add(new_interval)
                repo_obj.dev_intervals[db_user.user_github_id][db_branch.branch_name][db_file.file_path].add(new_interval)

        repo_obj.is_loaded_from_db = True
        repo_obj.is_dirty = False
        repo_obj.last_activity = time.time()

    async def save_repo_to_db(self, db, repo_name: str):
        repo_obj = self.repos[repo_name]

        repo_stmt = select(DBRepo.repository_id).where(DBRepo.repo_name == repo_name)
        repo_id_scalar = (await db.execute(repo_stmt)).scalar_one_or_none()
        
        if not repo_id_scalar:
            return

        branch_stmt = select(DBBranch.branch_id).where(DBBranch.repository_id == repo_id_scalar)
        file_stmt = select(DBFile.file_id).where(DBFile.branch_id.in_(branch_stmt))
        
        del_stmt = delete(Edit).where(Edit.file_id.in_(file_stmt))
        await db.execute(del_stmt)

        all_dev_ids = list(repo_obj.dev_intervals.keys())
        if not all_dev_ids:
            repo_obj.is_dirty = False
            await db.commit()
            return
            
        user_stmt = select(DBUser.user_github_id, DBUser.user_id).where(DBUser.user_github_id.in_(all_dev_ids))
        user_map = {row[0]: row[1] for row in (await db.execute(user_stmt)).all()}

        branch_file_stmt = (
            select(DBBranch.branch_name, DBFile.file_path, DBFile.file_id)
            .join(DBFile, DBBranch.branch_id == DBFile.branch_id)
            .where(DBBranch.repository_id == repo_id_scalar)
        )
        file_map = {(row[0], row[1]): row[2] for row in (await db.execute(branch_file_stmt)).all()}

        new_edits = []
        for dev_id, branches in repo_obj.dev_intervals.items():
            user_id = user_map.get(dev_id)
            if not user_id:
                continue
            
            for branch_name, files in branches.items():
                for file_path, intervals in files.items():
                    file_id = file_map.get((branch_name, file_path))
                    if not file_id or not intervals:
                        continue
                        
                    sample_interval = next(iter(intervals))
                    patch: PatchEvent = sample_interval.data

                    new_edits.append(Edit(
                        user_id=user_id,
                        file_id=file_id,
                        edit_timestamp=datetime.datetime.fromtimestamp(patch.timestamp),
                        edit_patch=patch.patch_text,
                        edit_base_commit=patch.base_commit,
                        edit_ranges=json.dumps(patch.touched_ranges)
                    ))
        
        if new_edits:
            db.add_all(new_edits)
            
        await db.commit()
        repo_obj.is_dirty = False

    def clear_all_dev_intervals(self, dev_id: str):
        """
        Remove all live intervals for a dev across every repo and branch.
        Called when a developer's WebSocket connection closes.
        """
        for repo in self.repos.values():
            if dev_id in repo.dev_intervals:
                for branch_name in list(repo.dev_intervals[dev_id].keys()):
                    repo.clear_dev_branch(dev_id, branch_name)

    async def patch_update(self, db, file: File, incoming_patch: PatchEvent):
        """
        Process an incoming patch from a developer and detect conflicts.

        The IntervalTree (repo.files) contains only live (uncommitted) developer edits,
        all in HEAD-relative line coordinates produced by `git diff HEAD`. This shared
        coordinate space makes same-branch overlap detection mathematically exact.

        Conflict reporting has two distinct layers:

        1. SAME-BRANCH LIVE CONFLICTS (conflict / conflicting_dev_lines)
           Exact line-level comparison. Both devs are on the same branch, so their
           diffWithHEAD patches are relative to the same HEAD commit. The IntervalTree
           overlap is authoritative.

        2. CROSS-BRANCH LIVE FILE CONFLICTS (cross_branch_live_files)
           File-level only. A feature-branch dev and a main-branch dev are editing the
           same file, but their HEAD-relative coordinates are different (feature HEAD ≠
           main HEAD). Comparing line numbers directly would produce false positives and
           false negatives, so we report only the file name as a coarse warning.

        3. COMMITTED BRANCH CONFLICTS (not in this response)
           What will actually conflict at merge time is handled by the branch-health
           endpoint via get_two_way_diff(), which uses merge-base coordinates for both
           sides and is always accurate.
        """
        repo_name = file.owner + "/" + file.repo
        repo = self.repos[repo_name]

        if not repo.is_loaded_from_db:
            await self._load_repo_from_db(db, repo_name)
            
        repo.last_activity = time.time()
        repo.is_dirty = True

        if repo.default_branch is None:
            repo.default_branch = await self.github_api.get_default_branch(
                db, file.owner, file.repo
            )

        latest_commit = await self.github_api.get_latest_commit_hash(
            db, file.owner, file.repo, incoming_patch.branch, file.path
        )
        if latest_commit is not None and incoming_patch.base_commit != latest_commit:
            # The client is behind — wipe their stale state and reject the patch.
            repo.clear_dev_branch(incoming_patch.dev_id, incoming_patch.branch)
            return {
                "ok": True,
                "type": "patch_update",
                "conflict": False,
                "outdated": True,
                "details": "Patch is not on top of the latest commit. Please pull the latest changes and try again.",
            }

        tree = repo.files[file.path]

        # ── Step 1: Replace this dev's previous intervals for this branch/file ────────
        # The client always sends a cumulative patch (diffWithHEAD), so we replace all
        # previously registered intervals rather than appending to them.
        for ival in list(repo.dev_intervals[incoming_patch.dev_id][incoming_patch.branch][file.path]):
            tree.discard(ival)
        repo.dev_intervals[incoming_patch.dev_id][incoming_patch.branch][file.path].clear()

        # Guard: empty touched_ranges means the file has no uncommitted changes at all.
        # Honour the wipe above (file is clean now) and return without re-adding anything.
        if not incoming_patch.touched_ranges:
            return {
                "ok": True,
                "type": "patch_update",
                "conflict": False,
                "conflicting_dev_lines": [],
                "cross_branch_live_files": [],
                "outdated": False,
                "details": "No-op patch: file has no uncommitted changes.",
            }

        # ── Step 2: Same-branch exact-line conflict detection ─────────────────────────
        conflicting_lines = set()

        for start, end in incoming_patch.touched_ranges:
            overlaps = tree.overlap(start, end + 1)

            for interval in overlaps:
                existing_patch = interval.data

                # Defensive: skip our own stale overlap (shouldn't happen after the
                # clear above, but guard against any race or data corruption).
                if existing_patch.dev_id == incoming_patch.dev_id:
                    continue

                # ── On the default branch: only care about other live main devs ──────
                # Main devs don't get warned about uncommitted feature-branch work.
                if incoming_patch.branch == repo.default_branch:
                    if existing_patch.branch != repo.default_branch:
                        continue

                # ── On a feature branch: only compare against the same feature branch ─
                # Cross-branch live conflicts are handled at file-level in Step 3.
                if incoming_patch.branch != repo.default_branch:
                    if existing_patch.branch != incoming_patch.branch:
                        continue

                # Compute the precise overlapping line numbers
                overlap_start = max(start, interval.begin)
                overlap_end = min(end + 1, interval.end)
                for line_num in range(overlap_start, overlap_end):
                    conflicting_lines.add(line_num)

            # Register the new interval in both the shared tree and the per-dev index
            new_interval = Interval(start, end + 1, incoming_patch)
            tree.add(new_interval)
            repo.dev_intervals[incoming_patch.dev_id][incoming_patch.branch][file.path].add(new_interval)

        # ── Step 3: Cross-branch live file conflict detection (feature branches only) ─
        # If any live devs on main are editing this same file, surface a coarse warning.
        # We cannot compare exact lines here because feature-HEAD coordinates and
        # main-HEAD coordinates are different (the branches have diverged).
        cross_branch_live_files = []
        if incoming_patch.branch != repo.default_branch:
            main_has_live_edits = any(
                ival.data.branch == repo.default_branch
                for ival in tree
            )
            if main_has_live_edits:
                cross_branch_live_files.append(file.path)

        return {
            "ok": True,
            "type": "patch_update",
            "conflict": bool(conflicting_lines),
            "conflicting_dev_lines": sorted(list(conflicting_lines)),
            "cross_branch_live_files": cross_branch_live_files,
            "invalid_patch": False,
            "outdated": False,
            "details": "Patch processed.",
        }

    def branch_update(
        self,
        dev_id: str,
        owner: str,
        repo_name: str,
        old_branch: str,
        new_branch: str,
        base_commit: str,
        new_base_commit=None,
    ):
        """
        Triggered when a developer switches branches.
        Clear their intervals on the old branch; the client will re-send patches for
        the new branch on its next keystroke.
        """
        print("Branch update:", dev_id, owner, repo_name, old_branch, "->", new_branch)
        repo = self.repos[owner + "/" + repo_name]
        if old_branch:
            repo.clear_dev_branch(dev_id, old_branch)

    def handle_push_sync(self, owner: str, repo_name: str, branch: str, file_path: str):
        """
        Invoked after a git push is detected via the GitHub webhook.

        Two things happen:
        1. Cached branch diff data is evicted (it is now stale because HEAD moved).
        2. All live developer intervals for the pushed branch/file are wiped.
           Their base_commit is outdated and they would be rejected on the next
           patch_update anyway; clearing eagerly keeps the tree consistent.

        Connected clients are notified separately via ConnectionManager.notify_branch()
        so they re-run diffWithHEAD and re-register their intervals immediately.
        """
        full_repo_name = owner + "/" + repo_name
        if full_repo_name not in self.repos:
            return

        repo = self.repos[full_repo_name]

        # ── Cache eviction ────────────────────────────────────────────────────────────
        if branch == repo.default_branch:
            # A push to main invalidates every feature-branch committed diff.
            self.github_api.clear_all_repo_diffs(owner, repo_name)
        else:
            # A push to a feature branch invalidates only that branch's diffs
            # in both comparison directions.
            default = repo.default_branch or "main"
            for key in [
                (owner, repo_name, default, branch),
                (owner, repo_name, branch, default),
            ]:
                if key in self.github_api.branch_diffs.cache:
                    del self.github_api.branch_diffs.cache[key]

        # ── Wipe live dev intervals for the pushed branch/file ────────────────────────
        tree = repo.files[file_path]
        for dev_id in list(repo.dev_intervals.keys()):
            intervals_to_remove = list(repo.dev_intervals[dev_id][branch][file_path])
            for ival in intervals_to_remove:
                tree.discard(ival)
            repo.dev_intervals[dev_id][branch][file_path].clear()
            
        repo.last_activity = time.time()
        repo.is_dirty = True
