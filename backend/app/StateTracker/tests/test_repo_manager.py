import pytest
import asyncio
import time
import os
import sys

# Bootstrap path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.StateTracker.RepoManager import RepoManager, Repo
from app.StateTracker.GithubAPI import GithubAPI, File, PatchEvent

# ---------------------------------------------------------------------------
# Mocks & Helpers
# ---------------------------------------------------------------------------
BASE_FILE = """\
def greet(name):
    print("Hello,", name)

def farewell(name):
    print("Goodbye,", name)
"""

PATCH_ALICE_LINE2 = """\
--- a/greet.py
+++ b/greet.py
@@ -2,1 +2,1 @@
-    print("Hello,", name)
+    print("Hi there,", name)
"""

PATCH_BOB_LINE2_CONFLICT = """\
--- a/greet.py
+++ b/greet.py
@@ -2,1 +2,1 @@
-    print("Hello,", name)
+    print("Howdy,", name)
"""

class MockDB:
    pass

class MockGithubAPI:
    def __init__(self, mock_default="main"):
        self.mock_default = mock_default
        self.mock_diffs = {}
        self.latest_commits = {} # (owner, repo, branch, path) -> sha
        self.branch_diffs = type('obj', (object,), {'cache': {}})()
        self.loaded_branches = set()

    async def get_latest_commit_hash(self, db, owner, repo, branch, path):
        return self.latest_commits.get((owner, repo, branch, path), "abc123")

    async def get_default_branch(self, db, owner, repo):
        return self.mock_default

    def get_branch_diff(self, owner, repo_name, base_ref, head_ref, repo, latest_commit_hash):
        diff_map = self.mock_diffs.get(head_ref, {})
        
        # Apply synthetic patches to repo
        for path, ranges in diff_map.items():
            for start, end in ranges:
                commit_patch = PatchEvent(
                    dev_id="github-commit",
                    base_commit=latest_commit_hash,
                    branch=head_ref,
                    timestamp=0,
                    patch_text="",
                    author="GitHub",
                    touched_ranges=((start, end),)
                )
                from intervaltree import Interval
                ival = Interval(start, end, commit_patch)
                repo.files[path].add(ival)
                repo.dev_intervals["github-commit"][head_ref][path].add(ival)
        
        return diff_map

    def clear_all_repo_diffs(self, owner, repo_name, repo):
        pass

def make_file(branch="feature/login", base_commit="abc123"):
    return File(owner="acme", repo="myapp", branch=branch, path="greet.py", base_commit=base_commit)

def make_patch(dev_id, branch, patch_text, touched_ranges, base_commit="abc123"):
    return PatchEvent(
        dev_id=dev_id,
        base_commit=base_commit,
        branch=branch,
        timestamp=time.time(),
        patch_text=patch_text,
        author=dev_id.capitalize(),
        touched_ranges=tuple(touched_ranges),
    )

def setup_rm():
    rm = RepoManager()
    rm.github_api = MockGithubAPI()
    file = make_file(branch="main", base_commit="abc123")
    db = MockDB()
    return rm, db, file

# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_strict_commit_rejection():
    """If base_commit is outdated, patch is rejected and local changes purged."""
    rm, db, file = setup_rm()
    rm.github_api.latest_commits[("acme", "myapp", "main", "greet.py")] = "new456" # DB has advanced!
    
    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)], base_commit="abc123")
    rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"].add("fake_interval")
    
    result = asyncio.run(rm.patch_update(db, file, alice_patch))
    
    assert result["outdated"] is True
    assert result["conflict"] is False
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 0

def test_clean_patch_accepted():
    rm, db, file = setup_rm()
    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)], base_commit="abc123")
    result = asyncio.run(rm.patch_update(db, file, alice_patch))
    
    assert result["conflict"] is False
    assert result["outdated"] is False
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 1

def test_cross_branch_uncommitted_conflict():
    """Two devs on DIFFERENT branches edit the same lines, uncommitted vs uncommitted."""
    rm, db, file_main = setup_rm()
    file_feature = make_file(branch="feature-x", base_commit="abc123")
    
    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))
    
    # Bob is on feature-x, touches same line
    bob_patch = make_patch("bob", "feature-x", PATCH_BOB_LINE2_CONFLICT, [(2, 2)])
    result = asyncio.run(rm.patch_update(db, file_feature, bob_patch))
    
    assert result["conflict"] is True
    assert 2 in result["conflicting_dev_lines"]

def test_branch_switch_purges_old():
    """branch_update safely wipes the old branch intervals for the user."""
    rm, db, file = setup_rm()
    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)])
    asyncio.run(rm.patch_update(db, file, alice_patch))
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]) == 1
    
    rm.branch_update("alice", "acme", "myapp", "main", "feature", "abc123")
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 0

def test_global_push_sync_evicts_branch():
    """handle_push_sync completely removes all intervals for a branch globally."""
    rm, db, file = setup_rm()
    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)])
    asyncio.run(rm.patch_update(db, file, alice_patch))
    
    rm.handle_push_sync("acme", "myapp", "main", "greet.py")
    assert len(rm.repos["acme/myapp"].files["greet.py"]) == 0
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 0

def test_fresh_branch_no_commits():
    """If a branch has no commits relative to main, fetching diff returns empty, no conflict occurs naturally."""
    rm, db, file_feature = setup_rm()
    file_feature = make_file(branch="fresh-branch", base_commit="abc123")
    
    # The cache has NOTHING for fresh-branch, meaning it returns {}
    alice_patch = make_patch("alice", "fresh-branch", PATCH_ALICE_LINE2, [(2, 2)])
    result = asyncio.run(rm.patch_update(db, file_feature, alice_patch))
    
    # Should be perfectly fine!
    assert result["conflict"] is False

def test_same_branch_commits_no_conflict():
    """A user on a branch should NOT conflict with the COMMITS of their very own branch."""
    rm, db, _ = setup_rm()
    file_feature = make_file(branch="feature-a", base_commit="abc123")
    
    # feature-a committed lines 10-20
    rm.github_api.mock_diffs["feature-a"] = {
        "greet.py": [(10, 20)]
    }
    
    # Alice edits line 12 inside her own branch's committed scope
    alice_patch = make_patch("alice", "feature-a", "", [(12, 12)])
    result = asyncio.run(rm.patch_update(db, file_feature, alice_patch))
    
    # This shouldn't conflict with itself! Yes it overlaps [10, 20), but it's her own branch.
    assert result["conflict"] is False 

def test_cross_branch_committed_conflict():
    """User on 'main' edits line, which conflicts with 'feature-a's COMMITTED lines."""
    rm, db, file_main = setup_rm()
    file_feature = make_file(branch="feature-a", base_commit="abc123")
    
    # feature-a committed lines 10-20
    rm.github_api.mock_diffs["feature-a"] = {
        "greet.py": [(10, 20)]
    }
    
    # Load feature-a's commits by faking an edit so it triggers the lazy fetch
    alice_patch = make_patch("alice", "feature-a", "", [(40, 40)])
    asyncio.run(rm.patch_update(db, file_feature, alice_patch))
    
    # Now Bob on main edits line 15. This SHOULD conflict with feature-a's commits!
    bob_patch = make_patch("bob", "main", "", [(15, 15)])
    result = asyncio.run(rm.patch_update(db, file_main, bob_patch))
    
    # Expectation: False. Devs on main are not warned about feature branch commits.
    assert result["conflict"] is False

def test_multiple_cross_branch_conflicts():
    """Alice, Bob, and Charlie on different branches all touch overlapping regions."""
    rm, db, file_main = setup_rm()
    file_b = make_file(branch="branch-b")
    file_c = make_file(branch="branch-c")
    
    # Alice on main: lines 10-12
    alice_patch = make_patch("alice", "main", "", [(10, 12)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))
    
    # Bob on branch-b: lines 11-13 (overlaps Alice on 11, 12)
    bob_patch = make_patch("bob", "branch-b", "", [(11, 13)])
    result_bob = asyncio.run(rm.patch_update(db, file_b, bob_patch))
    assert result_bob["conflict"] is True
    assert set(result_bob["conflicting_dev_lines"]) == {11, 12}
    
    # Charlie on branch-c: lines 12-14 (overlaps Alice on 12)
    # Bob on branch-b is hidden by the Main-Centric filter logic
    charlie_patch = make_patch("charlie", "branch-c", "", [(12, 14)])
    result_charlie = asyncio.run(rm.patch_update(db, file_c, charlie_patch))
    assert result_charlie["conflict"] is True
    assert set(result_charlie["conflicting_dev_lines"]) == {12}

def test_overlapping_committed_blocks():
    """Multiple branches have committed changes that overlap."""
    rm, db, file_main = setup_rm()
    file_a = make_file(branch="feat-a")
    file_b = make_file(branch="feat-b")
    
    # feat-a has committed lines 5-10
    rm.github_api.mock_diffs["feat-a"] = {"greet.py": [(5, 10)]}
    # feat-b has committed lines 8-15
    rm.github_api.mock_diffs["feat-b"] = {"greet.py": [(8, 15)]}
    
    # Trigger lazy load for both
    asyncio.run(rm.patch_update(db, file_a, make_patch("dev1", "feat-a", "", [(100, 100)])))
    asyncio.run(rm.patch_update(db, file_b, make_patch("dev2", "feat-b", "", [(200, 200)])))
    
    # Now Alice on main edits line 9. Should conflict with BOTH branches' commits.
    alice_patch = make_patch("alice", "main", "", [(9, 9)])
    result = asyncio.run(rm.patch_update(db, file_main, alice_patch))
    
    # Expectation: False. Main doesn't track feature branch overlaps.
    assert result["conflict"] is False

def test_conflict_resolution_by_moving():
    """A developer resolves a conflict by moving their edit away from the overlapping area."""
    rm, db, file_main = setup_rm()
    file_feature = make_file(branch="feature-x")
    
    # Alice on main edits line 10
    alice_patch = make_patch("alice", "main", "", [(10, 10)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))
    
    # Bob on feature-x edits line 10 -> Conflict
    bob_patch_1 = make_patch("bob", "feature-x", "", [(10, 10)])
    result1 = asyncio.run(rm.patch_update(db, file_feature, bob_patch_1))
    assert result1["conflict"] is True
    
    # Bob moves his edit to line 20 -> No Conflict
    bob_patch_2 = make_patch("bob", "feature-x", "", [(20, 20)])
    result2 = asyncio.run(rm.patch_update(db, file_feature, bob_patch_2))
    assert result2["conflict"] is False
    
    # Bob moves back to line 10 -> Conflict again
    result3 = asyncio.run(rm.patch_update(db, file_feature, bob_patch_1))
    assert result3["conflict"] is True

def test_push_sync_full_lifecycle():
    """Verify that push sync clears and then allows clean rebuild of state."""
    rm, db, file_main = setup_rm()
    file_feat = make_file(branch="feat-x")
    
    # 1. Setup a conflict
    alice_patch = make_patch("alice", "main", "", [(10, 10)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))
    
    bob_patch = make_patch("bob", "feat-x", "", [(10, 10)])
    result1 = asyncio.run(rm.patch_update(db, file_feat, bob_patch))
    assert result1["conflict"] is True
    
    # 2. Push sync occurs for feat-x
    # This should clear bob's intervals and the cached committed diffs for feat-x
    rm.handle_push_sync("acme", "myapp", "feat-x", "greet.py")
    
    # Verify Bob's intervals are gone, but Alice's remain
    assert len(rm.repos["acme/myapp"].dev_intervals["bob"]["feat-x"]["greet.py"]) == 0
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 1
    
    # 3. Bob sends a NEW patch on feat-x that still overlaps
    result2 = asyncio.run(rm.patch_update(db, file_feat, bob_patch))
    assert result2["conflict"] is True
    assert 10 in result2["conflicting_dev_lines"]

def test_hidden_branch_conflict():
    """
    Alice on main should NOT conflict with feat-x's COMMITTED lines
    following the 'Main-Centric' logic (main is the anchor, feature follows main).
    """
    rm, db, file_main = setup_rm()
    
    # feat-x has committed lines 10-20
    rm.github_api.mock_diffs["feat-x"] = {"greet.py": [(10, 20)]}
    
    # Alice edits line 15 on main
    alice_patch = make_patch("alice", "main", "", [(15, 15)])
    result = asyncio.run(rm.patch_update(db, file_main, alice_patch))
    
    # Expectation: No conflict for the person on main.
    assert result["conflict"] is False

def test_feature_tracks_main_conflict():
    """
    A developer on a feature branch SHOULD be warned about overlapping with MAIN commits.
    """
    rm, db, _ = setup_rm()
    file_feature = make_file(branch="feat-x")
    
    # main has hypothetical edits or we just assume its base is the baseline.
    # Actually, feature branches are diffed AGAINST main, so we lazy load main commits?
    # No, currently we load CURRENT branch commits. 
    # Let's say Bob is on main and has an UNCOMMITTED patch.
    file_main = make_file(branch="main")
    bob_patch = make_patch("bob", "main", "", [(10, 10)])
    asyncio.run(rm.patch_update(db, file_main, bob_patch))
    
    # Alice on feat-x edits line 10
    alice_patch = make_patch("alice", "feat-x", "", [(10, 10)])
    result = asyncio.run(rm.patch_update(db, file_feature, alice_patch))
    
    assert result["conflict"] is True
    assert 10 in result["conflicting_dev_lines"]

def test_custom_default_branch():
    """Verify that a custom branch (e.g., 'develop') works as the 'main' anchor."""
    rm = RepoManager()
    rm.github_api = MockGithubAPI(mock_default="develop")
    db = MockDB()
    
    file_dev = make_file(branch="develop")
    file_feat = make_file(branch="feature-1")
    
    # Alice on develop edits line 5
    alice_patch = make_patch("alice", "develop", "", [(5, 5)])
    asyncio.run(rm.patch_update(db, file_dev, alice_patch))
    
    # Bob on feature-1 edits line 5 -> SHOULD conflict with develop
    bob_patch = make_patch("bob", "feature-1", "", [(5, 5)])
    result = asyncio.run(rm.patch_update(db, file_feat, bob_patch))
    
    assert result["conflict"] is True
    assert 5 in result["conflicting_dev_lines"]

def test_no_conflict_with_self_committed():
    """Verify Alice on feature-1 does NOT conflict with committed code from feature-1."""
    rm = RepoManager()
    rm.github_api = MockGithubAPI()
    rm.github_api.mock_diffs = {"feature-1": {"greet.py": [(10, 20)]}}
    db = MockDB()
    
    file_f1 = make_file(branch="feature-1")
    
    # Alice edits line 10 (which is part of the committed diff)
    # This should reload the branch diff into the tree
    patch = make_patch("alice", "feature-1", "", [(10, 10)])
    result = asyncio.run(rm.patch_update(db, file_f1, patch))
    
    # Should NOT be a conflict (filtered out because it's the same branch's committed code)
    assert result["conflict"] is False

# ---------------------------------------------------------------------------
# Tests for GithubAPI.get_two_way_diff
# ---------------------------------------------------------------------------

class MockResponse:
    def __init__(self, status_code, data):
        self._data = data
        self.status_code = status_code
    def json(self):
        return self._data

def _make_compare_data(ahead_by, behind_by, files):
    """Build a minimal GitHub compare API response."""
    return {
        "ahead_by": ahead_by,
        "behind_by": behind_by,
        "files": [
            {
                "filename": fname,
                "patch": patch,
            }
            for fname, patch in files.items()
        ],
    }

def _hunk(orig_start, orig_len, new_start, new_len):
    return f"@@ -{orig_start},{orig_len} +{new_start},{new_len} @@\n context\n"

def test_two_way_diff_no_conflicts(monkeypatch):
    """Two branches changed different files / lines — no base conflicts."""
    api = GithubAPI()

    responses = [
        # forward: main...feature (feature added lines 10-15 in feature.py)
        MockResponse(200, _make_compare_data(3, 0, {"feature.py": _hunk(10, 5, 10, 8)})),
        # reverse: feature...main (main added lines 50-60 in main.py — different file)
        MockResponse(200, _make_compare_data(0, 3, {"main.py": _hunk(50, 10, 50, 12)})),
    ]
    call_count = [0]

    def fake_get(url, headers):
        resp = responses[call_count[0]]
        call_count[0] += 1
        return resp

    monkeypatch.setattr("app.StateTracker.GithubAPI.requests.get", fake_get)

    result = api.get_two_way_diff("acme", "myapp", "main", "feature")
    assert result["ahead_by"] == 3
    assert result["behind_by"] == 3
    assert result["base_conflicts"] == {}

def test_two_way_diff_detects_conflict(monkeypatch):
    """Same file, overlapping hunk ranges in merge-base coords → conflict."""
    api = GithubAPI()

    responses = [
        # forward: main...feature (feature changed lines 10-20 in auth.py)
        MockResponse(200, _make_compare_data(2, 0, {"auth.py": _hunk(10, 10, 10, 12)})),
        # reverse: feature...main  (main changed lines 15-25 in auth.py — overlaps!)
        MockResponse(200, _make_compare_data(0, 4, {"auth.py": _hunk(15, 10, 15, 9)})),
    ]
    call_count = [0]

    def fake_get(url, headers):
        resp = responses[call_count[0]]
        call_count[0] += 1
        return resp

    monkeypatch.setattr("app.StateTracker.GithubAPI.requests.get", fake_get)

    result = api.get_two_way_diff("acme", "myapp", "main", "feature")
    assert result["base_conflicts"] != {}
    assert "auth.py" in result["base_conflicts"]

def test_two_way_diff_cache_prevents_refetch(monkeypatch):
    """Second call to get_two_way_diff uses cache; no extra HTTP requests fired."""
    api = GithubAPI()
    call_count = [0]

    def fake_get(url, headers):
        call_count[0] += 1
        return MockResponse(200, _make_compare_data(1, 1, {}))

    monkeypatch.setattr("app.StateTracker.GithubAPI.requests.get", fake_get)

    api.get_two_way_diff("acme", "myapp", "main", "feature")
    assert call_count[0] == 2  # one per direction

    api.get_two_way_diff("acme", "myapp", "main", "feature")
    assert call_count[0] == 2  # still 2 — both were cached

