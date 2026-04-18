import httpx
import re
from collections import OrderedDict
from dataclasses import dataclass
from .FileStates import PatchEvent
from intervaltree import Interval, IntervalTree


class LRUCache:
    def __init__(self, maxsize=1000):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)


@dataclass(frozen=True)
class File:
    owner: str
    repo: str
    branch: str
    path: str
    base_commit: str


class GithubAPI:
    def __init__(self, maxsize=1000, token=None):
        self.token = token
        self.latest_commits = LRUCache(maxsize)   # (owner, repo, branch, path) -> sha
        self.default_branches = LRUCache(maxsize)  # (owner, repo) -> branch_name
        # (owner, repo, base_ref, head_ref) -> (diff_map, ahead_by, behind_by)
        # diff_map: {filename -> [(start, end), ...]} in merge-base (-side) coordinates.
        self.branch_diffs = LRUCache(maxsize)

    async def get_default_branch(self, db, owner: str, repo: str) -> str:
        key = (owner, repo)
        cached = self.default_branches.get(key)
        if cached:
            return cached

        from app.db.models.models import Repository as DBRepo
        from sqlalchemy import select

        repo_full_name = f"{owner}/{repo}"
        stmt = select(DBRepo.repo_default_branch).where(DBRepo.repo_name == repo_full_name)
        result = await db.execute(stmt)
        default_branch = result.scalar_one_or_none() or "main"

        self.default_branches.put(key, default_branch)
        return default_branch

    async def get_latest_commit_hash(self, db, owner: str, repo: str, branch: str, path: str) -> str | None:
        key = (owner, repo, branch, path)

        if self.latest_commits.get(key) is not None:
            return self.latest_commits.get(key)

        from app.db.models.models import File as DBFile, Branch as DBBranch, Repository as DBRepo
        from sqlalchemy import select

        repo_full_name = f"{owner}/{repo}"
        stmt = (
            select(DBFile.file_latest_commit)
            .join(DBBranch, DBFile.branch_id == DBBranch.branch_id)
            .join(DBRepo, DBBranch.repository_id == DBRepo.repository_id)
            .where(
                DBRepo.repo_name == repo_full_name,
                DBBranch.branch_name == branch,
                DBFile.file_path == path
            )
        )
        result = await db.execute(stmt)
        sha = result.scalar_one_or_none()

        if sha:
            self.latest_commits.put(key, sha)

        return sha

    def update_latest_commit(self, owner: str, repo: str, branch: str, path: str, sha: str):
        key = (owner, repo, branch, path)
        self.latest_commits.put(key, sha)

    async def get_branch_diff(self, owner: str, repo_name: str, base_ref: str, head_ref: str) -> dict:
        """
        Fetches and caches the committed diff between two branches in merge-base coordinates.

        Returns diff_map: {filename -> [(start, end), ...]} where line ranges are from
        the '-' (merge-base) side of the unified diff hunks.

        IMPORTANT: This method does NOT inject synthetic intervals into any IntervalTree.
        The diff_map is pure data used by callers directly. This avoids the coordinate
        system mismatch that occurred when mixing merge-base coordinates (these diffs)
        with HEAD-relative coordinates (live developer intervals).
        """
        key = (owner, repo_name, base_ref, head_ref)
        cached = self.branch_diffs.get(key)
        if cached is not None:
            return cached[0]  # (diff_map, ahead_by, behind_by) — only diff_map needed here

        url = f"https://api.github.com/repos/{owner}/{repo_name}/compare/{base_ref}...{head_ref}"
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers)

        if r.status_code != 200:
            return {}

        data = r.json()
        ahead_by = data.get("ahead_by", 0)
        behind_by = data.get("behind_by", 0)
        diff_map = {}
        for file_obj in data.get("files", []):
            patch_str = file_obj.get("patch")
            if not patch_str:
                continue
            ranges = []
            for match in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", patch_str, re.MULTILINE):
                start = int(match.group(1))
                length = int(match.group(2)) if match.group(2) else 1
                ranges.append((start, start + length if length > 0 else start + 1))
            diff_map[file_obj["filename"]] = ranges

        self.branch_diffs.put(key, (diff_map, ahead_by, behind_by))
        return diff_map

    def clear_all_repo_diffs(self, owner: str, repo_name: str):
        """
        Invalidate all branch comparison caches for a specific repository.
        Called when the default branch is pushed (all feature diffs become stale).
        """
        stale_keys = [
            k for k in list(self.branch_diffs.cache.keys())
            if k[0] == owner and k[1] == repo_name
        ]
        for k in stale_keys:
            del self.branch_diffs.cache[k]

    async def _fetch_compare(
        self,
        owner: str,
        repo_name: str,
        base_ref: str,
        head_ref: str,
        token: str = None
    ) -> tuple[int, int, dict]:
        """
        Fetch a GitHub compare response and return (ahead_by, behind_by, diff_map).
        diff_map: {filename -> [(start, end), ...]} in merge-base (-) coordinates.
        Results are cached in self.branch_diffs.
        """
        key = (owner, repo_name, base_ref, head_ref)
        cached = self.branch_diffs.get(key)
        if cached is not None:
            diff_map, ahead, behind = cached
            return ahead, behind, diff_map

        url = f"https://api.github.com/repos/{owner}/{repo_name}/compare/{base_ref}...{head_ref}"
        headers = {"Accept": "application/vnd.github+json"}
        _token = token or self.token
        if _token:
            headers["Authorization"] = f"Bearer {_token}"

        async with httpx.AsyncClient() as client:
            r = await client.get(url, headers=headers)

        if r.status_code != 200:
            return 0, 0, {}

        data = r.json()
        ahead_by = data.get("ahead_by", 0)
        behind_by = data.get("behind_by", 0)

        diff_map = {}
        for file_obj in data.get("files", []):
            patch_str = file_obj.get("patch")
            if not patch_str:
                continue
            ranges = []
            for match in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", patch_str, re.MULTILINE):
                start = int(match.group(1))
                length = int(match.group(2)) if match.group(2) else 1
                end = start + length if length > 0 else start + 1
                ranges.append((start, end))
            diff_map[file_obj["filename"]] = ranges

        self.branch_diffs.put(key, (diff_map, ahead_by, behind_by))
        return ahead_by, behind_by, diff_map

    async def get_two_way_diff(
        self,
        owner: str,
        repo_name: str,
        default_branch: str,
        feature_branch: str,
        token: str = None
    ) -> dict:
        """
        Compute the two-way committed diff between a feature branch and the default branch.

        Both directions are fetched using the '-' (merge-base) side of the hunk headers,
        so the line ranges are in the same coordinate space and overlap detection is accurate
        without needing actual file contents.

        Returns:
            {
                "ahead_by": int,       # commits feature is ahead of default
                "behind_by": int,      # commits feature is behind default
                "base_conflicts": {    # files with overlapping committed hunk ranges
                    "filename": [[start, end], ...]
                }
            }
        """
        # Forward: what feature changed relative to the merge-base
        ahead_by, _, feature_ranges = await self._fetch_compare(
            owner, repo_name, default_branch, feature_branch, token
        )
        # Reverse: what default changed relative to the merge-base
        _, behind_by, main_ranges = await self._fetch_compare(
            owner, repo_name, feature_branch, default_branch, token
        )

        ahead_by = ahead_by or 0
        behind_by = behind_by or 0

        # Find overlapping hunk ranges (merge-base coordinates on both sides)
        base_conflicts = {}
        all_files = set(feature_ranges.keys()) | set(main_ranges.keys())

        for filename in all_files:
            f_ranges = feature_ranges.get(filename, [])
            m_ranges = main_ranges.get(filename, [])

            if not f_ranges or not m_ranges:
                continue  # One side didn't touch this file — no conflict possible

            main_tree = IntervalTree()
            for start, end in m_ranges:
                if start < end:
                    main_tree.addi(start, end)

            conflicts = []
            for start, end in f_ranges:
                if start >= end:
                    continue
                overlaps = main_tree.overlap(start, end)
                if overlaps:
                    conflicts.append([start, end])

            if conflicts:
                base_conflicts[filename] = conflicts

        return {
            "ahead_by": ahead_by,
            "behind_by": behind_by,
            "base_conflicts": base_conflicts,
        }
