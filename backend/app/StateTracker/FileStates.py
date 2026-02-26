from collections import defaultdict
from dataclasses import dataclass

# frozen=True makes the object immutable and hashable
@dataclass(frozen=True)
class PatchEvent:
    dev_id: str
    base_commit: str
    timestamp: float
    patch_text: str
    author: str
    touched_ranges: tuple

    def __json__(self):
        return {
            "dev_id": self.dev_id,
            "base_commit": self.base_commit,
            "timestamp": self.timestamp,
            "patch_text": self.patch_text,
            "author": self.author,
            "touched_ranges": self.touched_ranges
        }

class FileStates:
    def __init__(self):
        self.patches_by_base = defaultdict(dict)
        # base_commit -> dev_id -> PatchEvent

    def add_patch(self, patch: PatchEvent):
        self.patches_by_base[patch.base_commit][patch.dev_id] = patch

    def get_patches_same_base(self, base_commit: str):
        return self.patches_by_base.get(base_commit, {}).values()

    def get_devs_patch(self, dev_id: str, base_commit: str):
        return self.patches_by_base.get(base_commit, {}).get(dev_id)

    def remove_patch(self, patch: PatchEvent):
        base_map = self.patches_by_base.get(patch.base_commit)
        if base_map:
            base_map.pop(patch.dev_id, None)