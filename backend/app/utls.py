from .StateTracker.FileStates import PatchEvent
from .StateTracker.GitMock import GitMock
from .StateTracker.FileCache import FileCache, File
import re
import time

HUNK_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@')

def extract_hunk_ranges(patch_text: str):
    """
    Extract base-side line ranges from unified diff.
    Returns sorted list of (start, end) inclusive.
    """
    ranges = []

    for line in patch_text.splitlines():
        match = HUNK_RE.match(line)
        if match:
            start = int(match.group(1))
            length = int(match.group(2)) if match.group(2) else 1
            end = start + length - 1
            ranges.append((start, end))

    return sorted(ranges)


def parse_update(msg: dict):
    try:
        file = File(
            owner=msg["owner"],
            repo=msg["repo"],
            branch=msg["branch"],
            path=msg["path"],
            base_commit=msg["base_commit"],
        )
        patch = PatchEvent(
            dev_id=msg["dev_id"],
            base_commit=msg["base_commit"],
            timestamp=msg.get("timestamp", time.time()),
            patch_text=msg["patch"],
            author=msg.get("author", msg["dev_id"]),
            touched_ranges=tuple(
                tuple(r) for r in (
                    msg.get("touched_ranges") or
                    extract_hunk_ranges(msg["patch"])
                )
            ),
        )
        return file, patch
    except KeyError as e:
        raise ValueError(f"Missing required field: {e}")

