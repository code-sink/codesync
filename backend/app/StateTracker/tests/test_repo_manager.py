"""
Tests for RepoManager — all test cases from the mock-data design session.

FileCache is monkey-patched so no real GitHub API calls are made.
Run with:
    cd codesync/backend
    uv run python -m pytest app/StateTracker/tests/test_repo_manager.py -v
"""
import time
import sys
import os
import unittest

# ---------------------------------------------------------------------------
# Path bootstrap so the module can be imported when run directly or via pytest
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.StateTracker.RepoManager import RepoManager
from app.StateTracker.FileCache import File
from app.StateTracker.FileStates import PatchEvent

# ---------------------------------------------------------------------------
# Shared base content used across all tests
# ---------------------------------------------------------------------------
BASE_FILE = """\
def greet(name):
    print("Hello,", name)

def farewell(name):
    print("Goodbye,", name)
"""

# Unified-diff patches that apply cleanly to BASE_FILE
PATCH_ALICE_LINE2 = """\
--- a/greet.py
+++ b/greet.py
@@ -2,1 +2,1 @@
-    print("Hello,", name)
+    print("Hi there,", name)
"""

PATCH_BOB_LINE5 = """\
--- a/greet.py
+++ b/greet.py
@@ -5,1 +5,1 @@
-    print("Goodbye,", name)
+    print("See ya,", name)
"""

# Bob edits the SAME line as Alice — will conflict
PATCH_BOB_LINE2_CONFLICT = """\
--- a/greet.py
+++ b/greet.py
@@ -2,1 +2,1 @@
-    print("Hello,", name)
+    print("Howdy,", name)
"""

PATCH_GARBAGE = "this is not a valid unified diff at all"


def make_file(branch="feature/login", base_commit="abc123"):
    return File(
        owner="acme",
        repo="myapp",
        branch=branch,
        path="greet.py",
        base_commit=base_commit,
    )


def make_repo_manager(file: File, content: str = BASE_FILE) -> RepoManager:
    """Build a RepoManager with its FileCache pre-seeded so GitHub is never hit."""
    rm = RepoManager()
    rm.file_cache.put_file_content(file, content)
    return rm


# ---------------------------------------------------------------------------
# Helper to build a PatchEvent without having to repeat all fields every time
# ---------------------------------------------------------------------------
def make_patch(dev_id, patch_text, touched_ranges, base_commit="abc123", author=None):
    return PatchEvent(
        dev_id=dev_id,
        base_commit=base_commit,
        timestamp=time.time(),
        patch_text=patch_text,
        author=author or dev_id.capitalize(),
        touched_ranges=tuple(touched_ranges),
    )


# ===========================================================================
# Test Cases
# ===========================================================================

class TestNoConflict(unittest.TestCase):
    """Two devs edit completely different lines — no conflict expected."""

    def setUp(self):
        self.file = make_file()
        self.rm = make_repo_manager(self.file)

    def test_first_patch_is_clean(self):
        alice_patch = make_patch("alice", PATCH_ALICE_LINE2, [(2, 2)])
        result = self.rm.patch_update(self.file, alice_patch)
        self.assertFalse(result["conflict"], "First patch should never conflict")
        self.assertFalse(result["invalid_patch"])

    def test_disjoint_patches_no_conflict(self):
        alice_patch = make_patch("alice", PATCH_ALICE_LINE2, [(2, 2)])
        bob_patch = make_patch("bob", PATCH_BOB_LINE5, [(5, 5)])

        r1 = self.rm.patch_update(self.file, alice_patch)
        r2 = self.rm.patch_update(self.file, bob_patch)

        self.assertFalse(r1["conflict"], "Alice's patch (line 2) should be clean")
        self.assertFalse(r2["conflict"], "Bob's patch (line 5) should be clean — different line")

    def test_dev_workspace_updated_on_patch(self):
        """dev_workspaces must be populated so branch_update can find the file."""
        alice_patch = make_patch("alice", PATCH_ALICE_LINE2, [(2, 2)])
        self.rm.patch_update(self.file, alice_patch)

        workspace_key = (self.file.owner, self.file.repo, self.file.branch, self.file.base_commit)
        self.assertIn(
            self.file.path,
            self.rm.dev_workspaces["alice"][workspace_key],
            "patch_update should register the file path in dev_workspaces",
        )


class TestConflict(unittest.TestCase):
    """Two devs edit the same line with different content — conflict expected for the second."""

    def setUp(self):
        self.file = make_file()
        self.rm = make_repo_manager(self.file)
        # Alice gets in first — clean
        self.alice_patch = make_patch("alice", PATCH_ALICE_LINE2, [(2, 2)])
        self.rm.patch_update(self.file, self.alice_patch)

    def test_conflicting_patch_detected(self):
        bob_patch = make_patch("bob", PATCH_BOB_LINE2_CONFLICT, [(2, 2)])
        result = self.rm.patch_update(self.file, bob_patch)

        self.assertTrue(result["conflict"], "Overlapping edits on the same line should conflict")
        self.assertFalse(result["invalid_patch"])

    def test_conflicting_patches_lists_alice(self):
        bob_patch = make_patch("bob", PATCH_BOB_LINE2_CONFLICT, [(2, 2)])
        result = self.rm.patch_update(self.file, bob_patch)

        conflicting_dev_ids = {p[0]["dev_id"] for p in result["conflicting_patches"]}
        self.assertIn("alice", conflicting_dev_ids, "Alice's patch should be in the conflict list")

    def test_conflicting_patches_is_list(self):
        """Response must be JSON-serialisable (list, not set)."""
        bob_patch = make_patch("bob", PATCH_BOB_LINE2_CONFLICT, [(2, 2)])
        result = self.rm.patch_update(self.file, bob_patch)

        self.assertIsInstance(result["conflicting_patches"], list)


class TestInvalidPatch(unittest.TestCase):
    """Patch text that can't be applied to the base content."""

    def setUp(self):
        self.file = make_file()
        self.rm = make_repo_manager(self.file)

    def test_garbage_patch_marked_invalid(self):
        bad_patch = make_patch("charlie", PATCH_GARBAGE, [(1, 3)])
        result = self.rm.patch_update(self.file, bad_patch)

        self.assertTrue(result["invalid_patch"], "Garbage diff should be flagged as invalid")
        self.assertFalse(result["conflict"])

    def test_invalid_patch_not_stored(self):
        """An invalid patch should not be kept in FileStates."""
        bad_patch = make_patch("charlie", PATCH_GARBAGE, [(1, 3)])
        self.rm.patch_update(self.file, bad_patch)

        file_state = self.rm.repos["acmemyapp"].branches[self.file.branch].files[self.file.path]
        stored = file_state.get_devs_patch("charlie", self.file.base_commit)
        self.assertIsNone(stored, "Invalid patch must NOT be stored in FileStates")


class TestBranchUpdate(unittest.TestCase):
    """Developer switches branches — patch migrated, old branch cleared."""

    def setUp(self):
        self.old_branch = "feature/login"
        self.new_branch = "feature/signup"
        self.file = make_file(branch=self.old_branch)
        self.rm = make_repo_manager(self.file)

        # Alice submits a patch on the old branch
        self.alice_patch = make_patch("alice", PATCH_ALICE_LINE2, [(2, 2)])
        self.rm.patch_update(self.file, self.alice_patch)

    def test_patch_moved_to_new_branch(self):
        self.rm.branch_update(
            dev_id="alice",
            owner="acme",
            repo_name="myapp",
            old_branch=self.old_branch,
            new_branch=self.new_branch,
            base_commit="abc123",
        )

        new_file_state = self.rm.repos["acmemyapp"].branches[self.new_branch].files["greet.py"]
        patch_on_new = new_file_state.get_devs_patch("alice", "abc123")
        self.assertIsNotNone(patch_on_new, "Patch should have been migrated to the new branch")
        self.assertEqual(patch_on_new.patch_text, PATCH_ALICE_LINE2)

    def test_patch_removed_from_old_branch(self):
        self.rm.branch_update(
            dev_id="alice",
            owner="acme",
            repo_name="myapp",
            old_branch=self.old_branch,
            new_branch=self.new_branch,
            base_commit="abc123",
        )

        old_file_state = self.rm.repos["acmemyapp"].branches[self.old_branch].files["greet.py"]
        patch_on_old = old_file_state.get_devs_patch("alice", "abc123")
        self.assertIsNone(patch_on_old, "Patch should be gone from the old branch after migration")

    def test_old_workspace_cleared(self):
        self.rm.branch_update(
            dev_id="alice",
            owner="acme",
            repo_name="myapp",
            old_branch=self.old_branch,
            new_branch=self.new_branch,
            base_commit="abc123",
        )
        old_ws = self.rm.dev_workspaces["alice"][("acme", "myapp", self.old_branch, "abc123")]
        self.assertEqual(len(old_ws), 0, "Old workspace entry should be cleared after branch switch")


class TestBaseCommitUpdate(unittest.TestCase):
    """Branch is pulled/rebased — patches rebased to new commit hash."""

    def setUp(self):
        self.file = make_file(base_commit="abc123")
        self.rm = make_repo_manager(self.file)

        self.alice_patch = make_patch("alice", PATCH_ALICE_LINE2, [(2, 2)])
        self.rm.patch_update(self.file, self.alice_patch)

    def test_patch_available_under_new_base(self):
        self.rm.base_commit_update(
            dev_id="alice",
            owner="acme",
            repo_name="myapp",
            branch="feature/login",
            old_base="abc123",
            new_base="def456",
        )

        file_state = self.rm.repos["acmemyapp"].branches["feature/login"].files["greet.py"]
        new_patch = file_state.get_devs_patch("alice", "def456")

        self.assertIsNotNone(new_patch, "Patch should exist under the new base commit")
        self.assertEqual(new_patch.base_commit, "def456")
        self.assertEqual(new_patch.patch_text, PATCH_ALICE_LINE2, "Patch text should be preserved")

    def test_patch_gone_under_old_base(self):
        self.rm.base_commit_update(
            dev_id="alice",
            owner="acme",
            repo_name="myapp",
            branch="feature/login",
            old_base="abc123",
            new_base="def456",
        )

        file_state = self.rm.repos["acmemyapp"].branches["feature/login"].files["greet.py"]
        old_patch = file_state.get_devs_patch("alice", "abc123")
        self.assertIsNone(old_patch, "Patch should be gone from the old base commit slot")

    def test_workspace_key_updated(self):
        self.rm.base_commit_update(
            dev_id="alice",
            owner="acme",
            repo_name="myapp",
            branch="feature/login",
            old_base="abc123",
            new_base="def456",
        )
        new_ws = self.rm.dev_workspaces["alice"][("acme", "myapp", "feature/login", "def456")]
        self.assertIn("greet.py", new_ws, "dev_workspaces should reflect the new base commit")


class TestRangesOverlap(unittest.TestCase):
    """Unit tests for the internal _ranges_overlap helper."""

    def setUp(self):
        self.rm = RepoManager()

    def test_no_overlap(self):
        self.assertFalse(self.rm._ranges_overlap([(1, 3)], [(5, 8)]))

    def test_adjacent_no_overlap(self):
        # (1,3) ends at 3, (4,6) starts at 4 — touching but not overlapping
        self.assertFalse(self.rm._ranges_overlap([(1, 3)], [(4, 6)]))

    def test_exact_overlap(self):
        self.assertTrue(self.rm._ranges_overlap([(2, 5)], [(2, 5)]))

    def test_partial_overlap(self):
        self.assertTrue(self.rm._ranges_overlap([(1, 5)], [(4, 8)]))

    def test_contained(self):
        self.assertTrue(self.rm._ranges_overlap([(1, 10)], [(3, 7)]))

    def test_empty_ranges_no_overlap(self):
        self.assertFalse(self.rm._ranges_overlap([], [(1, 5)]))
        self.assertFalse(self.rm._ranges_overlap([(1, 5)], []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
