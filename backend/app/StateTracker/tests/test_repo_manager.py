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
    """
    Minimal mock that replaces GithubAPI for unit tests.

    Key differences from the real API:
    - No HTTP calls are made.
    - get_branch_diff() returns a diff_map dict (no tree injection — matching the
      new architecture where GithubAPI never touches the IntervalTree directly).
    - branch_diffs cache is a simple dict-backed object so tests can pre-populate it.
    """

    def __init__(self, mock_default="main"):
        self.mock_default = mock_default
        self.mock_diffs = {}                # branch_name -> {path: [(start, end)]}
        self.latest_commits = {}           # (owner, repo, branch, path) -> sha
        self.branch_diffs = type('obj', (object,), {'cache': {}})()

    async def get_latest_commit_hash(self, db, owner, repo, branch, path):
        return self.latest_commits.get((owner, repo, branch, path), "abc123")

    async def get_default_branch(self, db, owner, repo):
        return self.mock_default

    async def get_branch_diff(self, owner, repo_name, base_ref, head_ref):
        """Return the diff_map for head_ref. No tree injection."""
        return self.mock_diffs.get(head_ref, {})

    def clear_all_repo_diffs(self, owner, repo_name):
        pass

    def update_latest_commit(self, owner, repo, branch, path, sha):
        self.latest_commits[(owner, repo, branch, path)] = sha


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
# Core lifecycle tests (unchanged behaviour)
# ---------------------------------------------------------------------------

def test_strict_commit_rejection():
    """If base_commit is outdated, patch is rejected and local changes purged."""
    rm, db, file = setup_rm()
    rm.github_api.latest_commits[("acme", "myapp", "main", "greet.py")] = "new456"

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


def test_empty_touched_ranges_is_noop():
    """
    An empty touched_ranges payload clears the dev's old intervals (the file is
    now clean) but does NOT assert a conflict. This prevents empty payloads from
    being misread as 'wipe then add nothing' race conditions.
    """
    rm, db, file = setup_rm()

    # First register some intervals
    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)])
    asyncio.run(rm.patch_update(db, file, alice_patch))
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 1

    # Then send an empty patch (file is clean)
    empty_patch = make_patch("alice", "main", "", [])
    result = asyncio.run(rm.patch_update(db, file, empty_patch))

    assert result["conflict"] is False
    assert result["conflicting_dev_lines"] == []
    # Intervals must be wiped
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 0


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


def test_fresh_branch_no_conflicts():
    """If a branch has no commits relative to main, there should be no conflict."""
    rm, db, _ = setup_rm()
    file_feature = make_file(branch="fresh-branch", base_commit="abc123")

    alice_patch = make_patch("alice", "fresh-branch", PATCH_ALICE_LINE2, [(2, 2)])
    result = asyncio.run(rm.patch_update(db, file_feature, alice_patch))

    assert result["conflict"] is False


# ---------------------------------------------------------------------------
# Same-branch exact-line conflict tests (IntervalTree is the authority here)
# ---------------------------------------------------------------------------

def test_same_branch_exact_line_conflict():
    """
    Alice and Bob are both on main and edit the SAME line.
    Both patches are in main-HEAD coordinates → IntervalTree overlap is exact.
    """
    rm, db, file_main = setup_rm()

    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))

    bob_patch = make_patch("bob", "main", PATCH_BOB_LINE2_CONFLICT, [(2, 2)])
    result = asyncio.run(rm.patch_update(db, file_main, bob_patch))

    assert result["conflict"] is True
    assert 2 in result["conflicting_dev_lines"]


def test_same_feature_branch_conflict():
    """Two devs on the same feature branch edit overlapping lines → exact conflict."""
    rm, db, _ = setup_rm()
    file_feat = make_file(branch="feature-x")

    alice_patch = make_patch("alice", "feature-x", "", [(5, 8)])
    asyncio.run(rm.patch_update(db, file_feat, alice_patch))

    bob_patch = make_patch("bob", "feature-x", "", [(7, 10)])
    result = asyncio.run(rm.patch_update(db, file_feat, bob_patch))

    assert result["conflict"] is True
    assert set(result["conflicting_dev_lines"]) == {7, 8}


def test_same_branch_no_overlap():
    """Two devs on main edit non-overlapping lines → no conflict."""
    rm, db, file_main = setup_rm()

    alice_patch = make_patch("alice", "main", "", [(1, 5)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))

    bob_patch = make_patch("bob", "main", "", [(10, 15)])
    result = asyncio.run(rm.patch_update(db, file_main, bob_patch))

    assert result["conflict"] is False


# ---------------------------------------------------------------------------
# Cross-branch live conflict tests (file-level only, coordinate-safe)
# ---------------------------------------------------------------------------

def test_cross_branch_uncommitted_conflict():
    """
    Alice (main) and Bob (feature-x) edit the same file.
    Their HEAD coordinates differ → no exact line conflict, but Bob receives
    a file-level warning in cross_branch_live_files.
    """
    rm, db, file_main = setup_rm()
    file_feature = make_file(branch="feature-x", base_commit="abc123")

    alice_patch = make_patch("alice", "main", PATCH_ALICE_LINE2, [(2, 2)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))

    bob_patch = make_patch("bob", "feature-x", PATCH_BOB_LINE2_CONFLICT, [(2, 2)])
    result = asyncio.run(rm.patch_update(db, file_feature, bob_patch))

    # No exact line conflict (different coordinate spaces)
    assert result["conflict"] is False
    # But Bob is warned at the file level that a main dev is also editing greet.py
    assert "greet.py" in result["cross_branch_live_files"]


def test_feature_tracks_main_conflict():
    """
    A developer on a feature branch edits a file that a main dev is also editing.
    Expect a file-level cross_branch warning (not an exact line conflict).
    """
    rm, db, _ = setup_rm()
    file_feature = make_file(branch="feat-x")
    file_main = make_file(branch="main")

    bob_patch = make_patch("bob", "main", "", [(10, 10)])
    asyncio.run(rm.patch_update(db, file_main, bob_patch))

    alice_patch = make_patch("alice", "feat-x", "", [(10, 10)])
    result = asyncio.run(rm.patch_update(db, file_feature, alice_patch))

    assert result["conflict"] is False
    assert "greet.py" in result["cross_branch_live_files"]


def test_cross_branch_no_warning_different_files():
    """
    Alice (main) edits file-A; Bob (feature) edits file-B.
    They're both live but on different files → no cross_branch_live_files warning.
    """
    rm, db, _ = setup_rm()

    file_main = File("acme", "myapp", "main", "file_a.py", "abc123")
    file_feat = File("acme", "myapp", "feature-x", "file_b.py", "abc123")

    alice_patch = make_patch("alice", "main", "", [(3, 5)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))

    bob_patch = make_patch("bob", "feature-x", "", [(3, 5)])
    result = asyncio.run(rm.patch_update(db, file_feat, bob_patch))

    assert result["conflict"] is False
    assert result["cross_branch_live_files"] == []


def test_main_dev_does_not_see_cross_branch_warning():
    """
    A dev on main editing a file that a feature-branch dev is also editing
    should NOT receive a cross_branch_live_files warning. Main only cares about
    other main devs.
    """
    rm, db, file_main = setup_rm()
    file_feat = make_file(branch="feature-x")

    # Feature dev registers first
    alice_patch = make_patch("alice", "feature-x", "", [(5, 10)])
    asyncio.run(rm.patch_update(db, file_feat, alice_patch))

    # Main dev edits same file
    bob_patch = make_patch("bob", "main", "", [(5, 10)])
    result = asyncio.run(rm.patch_update(db, file_main, bob_patch))

    # Bob is on main — he only cares about other main devs
    assert result["conflict"] is False
    assert result.get("cross_branch_live_files", []) == []


def test_multiple_cross_branch_conflicts():
    """
    Alice (main), Bob (branch-b), and Charlie (branch-c) all edit the same file.
    Bob and Charlie get file-level cross_branch warnings; no exact line conflicts.
    """
    rm, db, file_main = setup_rm()
    file_b = make_file(branch="branch-b")
    file_c = make_file(branch="branch-c")

    # Alice on main
    alice_patch = make_patch("alice", "main", "", [(10, 12)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))

    # Bob on branch-b: same file, overlapping lines but different coordinate space
    bob_patch = make_patch("bob", "branch-b", "", [(11, 13)])
    result_bob = asyncio.run(rm.patch_update(db, file_b, bob_patch))
    assert result_bob["conflict"] is False
    assert "greet.py" in result_bob["cross_branch_live_files"]

    # Charlie on branch-c: same file
    charlie_patch = make_patch("charlie", "branch-c", "", [(12, 14)])
    result_charlie = asyncio.run(rm.patch_update(db, file_c, charlie_patch))
    assert result_charlie["conflict"] is False
    assert "greet.py" in result_charlie["cross_branch_live_files"]


def test_custom_default_branch():
    """Verify that a custom default branch (e.g. 'develop') works as the anchor."""
    rm = RepoManager()
    rm.github_api = MockGithubAPI(mock_default="develop")
    db = MockDB()

    file_dev = make_file(branch="develop")
    file_feat = make_file(branch="feature-1")

    alice_patch = make_patch("alice", "develop", "", [(5, 5)])
    asyncio.run(rm.patch_update(db, file_dev, alice_patch))

    # Bob on feature-1: file-level cross_branch warning (develop is default)
    bob_patch = make_patch("bob", "feature-1", "", [(5, 5)])
    result = asyncio.run(rm.patch_update(db, file_feat, bob_patch))

    assert result["conflict"] is False
    assert "greet.py" in result["cross_branch_live_files"]


# ---------------------------------------------------------------------------
# Committed diff tests (main is the anchor; feature conflicts surface via
# branch-health endpoint, NOT live patch_update)
# ---------------------------------------------------------------------------

def test_same_branch_commits_no_conflict():
    """A user on a branch should NOT conflict with the COMMITS of their very own branch."""
    rm, db, _ = setup_rm()
    file_feature = make_file(branch="feature-a", base_commit="abc123")

    rm.github_api.mock_diffs["feature-a"] = {"greet.py": [(10, 20)]}

    alice_patch = make_patch("alice", "feature-a", "", [(12, 12)])
    result = asyncio.run(rm.patch_update(db, file_feature, alice_patch))

    # No synthetic committed intervals exist — mock_diffs are not injected any more.
    assert result["conflict"] is False


def test_cross_branch_committed_conflict():
    """
    A dev on main edits a line that a feature branch has committed changes on.
    Main devs are NOT warned about feature branch committed work — they only
    see conflicts with other live main devs.
    """
    rm, db, file_main = setup_rm()
    file_feature = make_file(branch="feature-a")

    rm.github_api.mock_diffs["feature-a"] = {"greet.py": [(10, 20)]}

    alice_patch = make_patch("alice", "feature-a", "", [(40, 40)])
    asyncio.run(rm.patch_update(db, file_feature, alice_patch))

    bob_patch = make_patch("bob", "main", "", [(15, 15)])
    result = asyncio.run(rm.patch_update(db, file_main, bob_patch))

    assert result["conflict"] is False


def test_overlapping_committed_blocks():
    """
    Two feature branches have committed overlapping lines.
    Alice on main edits within that zone — still no conflict for main in patch_update.
    Committed conflicts are surfaced via branch-health only.
    """
    rm, db, file_main = setup_rm()
    file_a = make_file(branch="feat-a")
    file_b = make_file(branch="feat-b")

    rm.github_api.mock_diffs["feat-a"] = {"greet.py": [(5, 10)]}
    rm.github_api.mock_diffs["feat-b"] = {"greet.py": [(8, 15)]}

    asyncio.run(rm.patch_update(db, file_a, make_patch("dev1", "feat-a", "", [(100, 100)])))
    asyncio.run(rm.patch_update(db, file_b, make_patch("dev2", "feat-b", "", [(200, 200)])))

    alice_patch = make_patch("alice", "main", "", [(9, 9)])
    result = asyncio.run(rm.patch_update(db, file_main, alice_patch))

    assert result["conflict"] is False


def test_no_conflict_with_self_committed():
    """Alice on feature-1 does NOT conflict with committed code from feature-1."""
    rm = RepoManager()
    rm.github_api = MockGithubAPI()
    rm.github_api.mock_diffs = {"feature-1": {"greet.py": [(10, 20)]}}
    db = MockDB()

    file_f1 = make_file(branch="feature-1")

    patch = make_patch("alice", "feature-1", "", [(10, 10)])
    result = asyncio.run(rm.patch_update(db, file_f1, patch))

    assert result["conflict"] is False


def test_hidden_branch_conflict():
    """
    Alice on main is NOT warned about feat-x's committed lines via patch_update.
    (Committed cross-branch conflicts are a branch-health concern.)
    """
    rm, db, file_main = setup_rm()
    rm.github_api.mock_diffs["feat-x"] = {"greet.py": [(10, 20)]}

    alice_patch = make_patch("alice", "main", "", [(15, 15)])
    result = asyncio.run(rm.patch_update(db, file_main, alice_patch))

    assert result["conflict"] is False


# ---------------------------------------------------------------------------
# Push sync lifecycle
# ---------------------------------------------------------------------------

def test_push_sync_full_lifecycle():
    """
    After a push, dev intervals are cleared and the tree accepts a fresh registration.
    Alice (main) remains; Bob's feat-x intervals are wiped by handle_push_sync.
    """
    rm, db, file_main = setup_rm()
    file_feat = make_file(branch="feat-x")

    # 1. Alice and Bob both editing line 10
    alice_patch = make_patch("alice", "main", "", [(10, 10)])
    asyncio.run(rm.patch_update(db, file_main, alice_patch))

    bob_patch = make_patch("bob", "feat-x", "", [(10, 10)])
    result1 = asyncio.run(rm.patch_update(db, file_feat, bob_patch))
    # Bob is on feature, Alice on main → file-level warning only
    assert result1["cross_branch_live_files"] == ["greet.py"]

    # 2. Push sync for feat-x
    rm.handle_push_sync("acme", "myapp", "feat-x", "greet.py")

    assert len(rm.repos["acme/myapp"].dev_intervals["bob"]["feat-x"]["greet.py"]) == 0
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 1

    # 3. Bob re-registers after re-sync → cross_branch_live_files still present
    result2 = asyncio.run(rm.patch_update(db, file_feat, bob_patch))
    assert result2["cross_branch_live_files"] == ["greet.py"]


# ---------------------------------------------------------------------------
# GithubAPI.get_two_way_diff — cache-based tests (no HTTP mocking needed)
# ---------------------------------------------------------------------------

def test_two_way_diff_no_conflicts():
    """Two branches changed different files/lines — no base conflicts."""
    api = GithubAPI()

    # Pre-populate the cache for both compare directions
    api.branch_diffs.put(
        ("acme", "myapp", "main", "feature"),
        ({"feature.py": [(10, 15)]}, 3, 0),
    )
    api.branch_diffs.put(
        ("acme", "myapp", "feature", "main"),
        ({"main.py": [(50, 60)]}, 0, 3),
    )

    result = asyncio.run(api.get_two_way_diff("acme", "myapp", "main", "feature"))
    assert result["ahead_by"] == 3
    assert result["behind_by"] == 3
    # Different files → no overlap
    assert result["base_conflicts"] == {}


def test_two_way_diff_detects_conflict():
    """Same file, overlapping hunk ranges → conflict detected."""
    api = GithubAPI()

    api.branch_diffs.put(
        ("acme", "myapp", "main", "feature"),
        ({"auth.py": [(10, 20)]}, 2, 0),
    )
    api.branch_diffs.put(
        ("acme", "myapp", "feature", "main"),
        ({"auth.py": [(15, 25)]}, 0, 4),
    )

    result = asyncio.run(api.get_two_way_diff("acme", "myapp", "main", "feature"))
    assert "auth.py" in result["base_conflicts"]


def test_two_way_diff_no_conflict_adjacent():
    """Adjacent but non-overlapping hunk ranges should NOT conflict."""
    api = GithubAPI()

    api.branch_diffs.put(
        ("acme", "myapp", "main", "feature"),
        ({"utils.py": [(1, 10)]}, 1, 0),
    )
    api.branch_diffs.put(
        ("acme", "myapp", "feature", "main"),
        ({"utils.py": [(10, 20)]}, 0, 1),  # starts exactly where feature ends
    )

    result = asyncio.run(api.get_two_way_diff("acme", "myapp", "main", "feature"))
    # Interval [1,10) and [10,20) are adjacent — IntervalTree.overlap(1,10) won't hit [10,20)
    assert result["base_conflicts"] == {}


def test_two_way_diff_cache_hit():
    """Second call uses cache; no re-computation of ranges."""
    api = GithubAPI()

    api.branch_diffs.put(
        ("acme", "myapp", "main", "feature"),
        ({}, 1, 0),
    )
    api.branch_diffs.put(
        ("acme", "myapp", "feature", "main"),
        ({}, 0, 1),
    )

    result1 = asyncio.run(api.get_two_way_diff("acme", "myapp", "main", "feature"))
    result2 = asyncio.run(api.get_two_way_diff("acme", "myapp", "main", "feature"))
    assert result1 == result2


def test_clear_all_repo_diffs():
    """clear_all_repo_diffs evicts all cached diffs for a repo."""
    api = GithubAPI()

    api.branch_diffs.put(("acme", "myapp", "main", "feat-a"), ({}, 1, 0))
    api.branch_diffs.put(("acme", "myapp", "feat-a", "main"), ({}, 0, 1))
    api.branch_diffs.put(("acme", "other-repo", "main", "feat-a"), ({}, 1, 0))

    api.clear_all_repo_diffs("acme", "myapp")

    assert ("acme", "myapp", "main", "feat-a") not in api.branch_diffs.cache
    assert ("acme", "myapp", "feat-a", "main") not in api.branch_diffs.cache
    # Other repo untouched
    assert ("acme", "other-repo", "main", "feat-a") in api.branch_diffs.cache


def test_clear_all_dev_intervals():
    """clear_all_dev_intervals removes a disconnected dev's intervals across all repos."""
    rm, db, file_main = setup_rm()
    file_feat = make_file(branch="feature-y")

    asyncio.run(rm.patch_update(db, file_main, make_patch("alice", "main", "", [(1, 5)])))
    asyncio.run(rm.patch_update(db, file_feat, make_patch("alice", "feature-y", "", [(10, 15)])))

    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 1
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["feature-y"]["greet.py"]) == 1

    rm.clear_all_dev_intervals("alice")

    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["main"]["greet.py"]) == 0
    assert len(rm.repos["acme/myapp"].dev_intervals["alice"]["feature-y"]["greet.py"]) == 0
    # Tree must also be clean
    assert len(rm.repos["acme/myapp"].files["greet.py"]) == 0
