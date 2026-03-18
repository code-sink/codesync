from .FileStates import PatchEvent
from .GithubAPI import GithubAPI, File
from collections import defaultdict
from intervaltree import IntervalTree, Interval

class Repo:
    def __init__(self):
        self.files = defaultdict(IntervalTree) # file_path -> IntervalTree of [line start, line end) -> PatchEvent
        self.default_branch = None
        # dev_id -> branch -> file_path -> set of interval_obj
        self.dev_intervals = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))

        
    def clear_dev_branch(self, dev_id: str, branch_name: str):
        """Removal of all local intervals for a dev on a specific branch"""
        for file_path, intervals in list(self.dev_intervals[dev_id][branch_name].items()):
            for interval_obj in list(intervals):
                self.files[file_path].discard(interval_obj)
        self.dev_intervals[dev_id][branch_name].clear()
        


# class Branch:
#     def __init__(self):
#         # file_path -> FileStates
#         self.files = defaultdict(FileStates)


class RepoManager:
    
    def __init__(self):
        self.repos = defaultdict(Repo)
        self.github_api = GithubAPI()

    async def patch_update(self, db, file: File, incoming_patch: PatchEvent):
        repo = self.repos[file.owner + "/" + file.repo]
        
        if repo.default_branch is None:
            repo.default_branch = await self.github_api.get_default_branch(db, file.owner, file.repo)

        latest_commit = await self.github_api.get_latest_commit_hash(db, file.owner, file.repo, incoming_patch.branch, file.path)
        print("LATEST COMMIT: ", latest_commit)
        if latest_commit is not None and incoming_patch.base_commit != latest_commit:
            # Wipe local changes from our system because they are invalid/outdated
            repo.clear_dev_branch(incoming_patch.dev_id, incoming_patch.branch)
            return {
                "conflict": False, 
                "outdated": True, 
                "details": "Patch is not on top of the latest commit. Please pull the latest changes and try again."
                }

        tree = repo.files[file.path]

        if incoming_patch.branch != repo.default_branch:           
            self.github_api.get_branch_diff(file.owner, file.repo, repo.default_branch, incoming_patch.branch, repo, latest_commit)
            

        # 3. Cleanup previous intervals for this user/branch/file
        for ival in list(repo.dev_intervals[incoming_patch.dev_id][incoming_patch.branch][file.path]):
            tree.discard(ival)
        repo.dev_intervals[incoming_patch.dev_id][incoming_patch.branch][file.path].clear()

        conflicting_lines = set()

        # 4. Detect Conflicts (Pure Coordinate Overlap) and Add New Intervals
        for start, end in incoming_patch.touched_ranges:
            overlaps = tree.overlap(start, end + 1)
            
            for interval in overlaps:
                existing_patch = interval.data
                
                # Ignore overlaps with COMMITS that belong to the SAME branch
                # A branch does not conflict with its own commits!
                if existing_patch.dev_id == "github-commit" and existing_patch.branch == incoming_patch.branch:
                    continue
                
                # --- MAIN-CENTRIC LOGIC ---
                # 1. If I am on MAIN: I only care about other patches on MAIN.
                if incoming_patch.branch == repo.default_branch:
                    if existing_patch.branch != repo.default_branch:
                        continue
                
                # 2. If I am on a FEATURE: I care about MAIN (both committed and uncommitted).
                if incoming_patch.branch != repo.default_branch:    
                    # for now only care about feature branch vs main conflicts and within this feature branch conflicts.
                    if existing_patch.branch != repo.default_branch and existing_patch.branch != incoming_patch.branch :
                        continue
                
                # We simply extract the intersecting line numbers
                overlap_start = max(start, interval.begin)
                overlap_end = min(end + 1, interval.end)
                for line_num in range(overlap_start, overlap_end):
                    conflicting_lines.add(line_num)

            # Store the interval with the data payload being the PatchEvent
            new_interval = Interval(start, end + 1, incoming_patch)
            tree.add(new_interval)
            repo.dev_intervals[incoming_patch.dev_id][incoming_patch.branch][file.path].add(new_interval)

        conflicting_branch_lines = []
        # Use file.path instead of missing incoming_patch.file_path
        if "github-commit" in repo.dev_intervals and incoming_patch.branch in repo.dev_intervals["github-commit"]:
            for ival in repo.dev_intervals["github-commit"][incoming_patch.branch][file.path]:
                conflicting_branch_lines.append((ival.begin, ival.end-1))
            
       
        return {
            "conflict": bool(conflicting_lines),
            "conflicting_dev_lines": sorted(list(conflicting_lines)),
            "conflicting_branch_lines": sorted(list(conflicting_branch_lines)),
            "invalid_patch": False,
            "outdated": False,
            "details": "Patch processed."
        }

            

    def branch_update(self, dev_id: str, owner: str, repo_name: str, old_branch: str, new_branch: str, base_commit: str, new_base_commit=None):
        """
        Triggered when a user switches branches.
        We simply clear their old intervals. The client will send fresh patches for the new branch.
        """
        print("Get branch update ", dev_id, owner, repo_name, old_branch, new_branch, base_commit, new_base_commit)
        repo = self.repos[owner + "/" + repo_name]
        repo.clear_dev_branch(dev_id, old_branch)

    def handle_push_sync(self, owner: str, repo_name: str, branch: str, file_path: str):
        full_repo_name = owner + "/" + repo_name
        if full_repo_name not in self.repos:
            return

        repo = self.repos[full_repo_name]
        
        # If the default branch was pushed, ALL feature branch diffs are potentially outdated
        if branch == repo.default_branch:
            self.github_api.clear_all_repo_diffs(owner, repo_name, repo)
        else:
            # Clear only the specific diff for this branch
            diff_key = (owner, repo_name, repo.default_branch or "main", branch)
            if diff_key in self.github_api.branch_diffs.cache:
                del self.github_api.branch_diffs.cache[diff_key]
            
            # 1. Clear intervals for this branch specifically
            if "github-commit" in repo.dev_intervals:
                for path, intervals in list(repo.dev_intervals["github-commit"][branch].items()):
                    for ival in list(intervals):
                        repo.files[path].discard(ival)
                repo.dev_intervals["github-commit"][branch].clear()
    

        # Remove all existing intervals (uncommitted and synthetic committed) for this branch/file
        # This forces the slate clean. They will be rebuilt on the exact next keystroke.
        tree = repo.files[file_path]
        
        # We must collect ALL devs who had an interval on this branch to purge them
        for dev_id in list(repo.dev_intervals.keys()):
            intervals_to_remove = list(repo.dev_intervals[dev_id][branch][file_path])
            for ival in intervals_to_remove:
                tree.discard(ival)
            repo.dev_intervals[dev_id][branch][file_path].clear()
    
    def get_active_devs(self, owner: str, repo_name: str, branch: str, inactivity_threshold: int = 900) -> dict:
        """
        Returns active developers grouped by branch and file.
        Filters out devs who haven't saved in inactivity_threshold seconds (default 15 min).
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
