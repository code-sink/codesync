import whatthepatch
from merge3 import Merge3
from typing import Tuple, Optional


class GitMock:
    """
    Git operations for merge conflict detection.
    """

    def __init__(self):
        pass

    def apply_patch(self, base_content: str, patch_text: str):
        try:
            diffs = list(whatthepatch.parse_patch(patch_text))
            if not diffs:
                return None
            result = whatthepatch.apply_diff(diffs[0], base_content.splitlines())
            if result is None:
                return None
            return "\n".join(result) + ("\n" if base_content.endswith("\n") else "")
        except Exception:
            return None

    def check_merge_conflict(self, base_content: str, existing_content: str, incoming_content: str):
        """
        Perform a git-standard 3-way merge using the merge3 library.

        Returns:
            - conflict: bool
            - merged_content: str (the merged result, or conflict-marked content)
        """
        m = Merge3(
            base_content.splitlines(True),
            existing_content.splitlines(True),
            incoming_content.splitlines(True),
        )
        merged_lines = list(m.merge_lines(name_a="existing", name_b="incoming"))
        merged = "".join(merged_lines)

        conflict = "<<<<<<<" in merged
        return conflict, merged