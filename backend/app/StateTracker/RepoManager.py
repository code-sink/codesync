from .FileStates import FileStates, PatchEvent
from .FileCache import FileCache, File
from .GitMock import GitMock
from collections import defaultdict

class Repo:
    def __init__(self):
        self.branches = defaultdict(Branch)


class Branch:
    def __init__(self):
        # file_path -> FileStates
        self.files = defaultdict(FileStates)


class RepoManager:
    
    def __init__(self):
        self.repos = defaultdict(Repo)
        self.file_cache = FileCache()
        self.git_mock = GitMock()
        self.dev_workspaces = defaultdict(lambda: defaultdict(set)) # of dev -> (owner, repo, branch, base_commit) -> set of file paths user edited locally 
        # ^ this is to find their local "changes" faster. 

    def _ranges_overlap(self, ranges_a, ranges_b):
        i = j = 0

        while i < len(ranges_a) and j < len(ranges_b):
            a_start, a_end = ranges_a[i]
            b_start, b_end = ranges_b[j]

            if a_end < b_start:
                i += 1
            elif b_end < a_start:
                j += 1
            else:
                return True  

        return False

    
    def patch_update(self, file: File, incoming_patch: PatchEvent):

        repo = self.repos[file.owner + file.repo]
        branch = repo.branches[file.branch]
        file_state = branch.files[file.path]

        base_content = self.file_cache.get_file_content(file)

        incoming_content = self.git_mock.apply_patch(base_content, incoming_patch.patch_text)

        if incoming_content is None: 
            # the patch doesn't apply to the base commit, it's invalid. We could be getting the wrong base commit.
            return {
                "conflict": False,
                "invalid_patch": True
            }

        conflicting_patches = set()

        for existing_patch in file_state.get_patches_same_base(file.base_commit):
            # if edit ranges don't overlap, skip expensive merge
            if not self._ranges_overlap( incoming_patch.touched_ranges, existing_patch.touched_ranges ):
                continue

            # Otherwise do real mock git merge to detect conflicts
            existing_content = self.git_mock.apply_patch(base_content, existing_patch.patch_text)

            conflict, content = self.git_mock.check_merge_conflict(base_content, existing_content, incoming_content)

            if conflict:
                conflicting_patches.add((existing_patch, content))

        file_state.add_patch(incoming_patch)
        self.dev_workspaces[incoming_patch.dev_id][(file.owner, file.repo, file.branch, file.base_commit)].add(file.path)
        if conflicting_patches:
            return {
                "conflict": True,
                "conflicting_patches": [(p.__json__(), c) for p, c in list(conflicting_patches)],
                "invalid_patch": False
            }

        return {
            "conflict": False,
            "invalid_patch": False
        }
            

    def branch_update(self, dev_id: str, owner: str, repo_name: str, old_branch: str, new_branch: str, base_commit: str, new_base_commit = None):
        """
        Triggered when a user switches branches.
        Copies/migrates their current workspace patches to the new branch without changing base commit.
        """
        for file_path in self.dev_workspaces[dev_id][(owner, repo_name, old_branch, base_commit)]:
            file_state = self.repos[owner + repo_name].branches[old_branch].files[file_path] 
            patch = file_state.get_devs_patch(dev_id, base_commit)
            if not patch:
                continue
            file_state.remove_patch(patch)
            self.dev_workspaces[dev_id][(owner, repo_name, new_branch, base_commit)].add(file_path)
            self.repos[owner + repo_name].branches[new_branch].files[file_path].add_patch(patch)
        
        self.dev_workspaces[dev_id][(owner, repo_name, old_branch, base_commit)] = set()

        if new_base_commit is not None:
            self.base_commit_update(dev_id, owner, repo_name, new_branch, base_commit, new_base_commit)


    def base_commit_update(self, dev_id:str, owner: str, repo_name: str, branch: str, old_base: str, new_base: str):
        """
        Triggered when a branch advances its base commit (pull/rebase).
        Updates all stored patches for the user in this branch to the new base commit.
        """
        for file_path in self.dev_workspaces[dev_id][(owner, repo_name, branch, old_base)]:
            file_state = self.repos[owner + repo_name].branches[branch].files[file_path] 
            patch = file_state.get_devs_patch(dev_id, old_base)
            file_state.remove_patch(patch)

            new_patch = PatchEvent(
                dev_id=patch.dev_id,
                base_commit=new_base,
                timestamp=patch.timestamp,
                patch_text=patch.patch_text,
                author=patch.author,
                touched_ranges=patch.touched_ranges
            )

            file_state.add_patch(new_patch)
            self.dev_workspaces[dev_id][(owner, repo_name, branch, new_base)].add(file_path)
           
        
        self.dev_workspaces[dev_id][(owner, repo_name, branch, old_base)] = set()   
