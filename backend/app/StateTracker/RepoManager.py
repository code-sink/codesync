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
        repo = self.repos[file.owner + "/" + file.repo]

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
    
    def get_active_devs(self, owner: str, repo_name: str, branch: str, inactivity_threshold: int = 900) -> dict:
        """
        returns a snapshot containing active developers grouped by branch and file
        """
        repo_key = owner + "/" + repo_name
        if repo_key not in self.repos:
            return {}

        repo = self.repos[repo_key]
        now = datetime.now(timezone.utc).timestamp()
        result = {}

        for dev_id, branches in repo.dev_intervals.items():
            if dev_id == "github-commit":
                continue
            files = branches.get(branch, {})
            for file_path, intervals in files.items():
                if not intervals:
                    continue
                last_save = max(ival.data.timestamp for ival in intervals)
                if now - last_save > inactivity_threshold:
                    continue
                result.setdefault(branch, {}).setdefault(file_path, []).append({
                    "dev_id": dev_id,
                    "last_save": last_save
                })

        return result
