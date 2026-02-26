
import requests
import base64
from collections import OrderedDict
from dataclasses import dataclass

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

# frozen=True makes the object immutable and hashable
@dataclass(frozen=True)
class File:
    owner: str
    repo: str
    branch: str
    path: str
    base_commit: str
    
class FileCache:
    def __init__(self, maxsize=1000):
        self.cache = LRUCache(maxsize)

    def _get_file_content(self, key: File, token = None):
        # when token is provided, per repo our service gets 5k requests per hour. 
        # when token is not provided, we get 60 requests per hour.
        url = f"https://api.github.com/repos/{key.owner}/{key.repo}/contents/{key.path}"
        params = {"ref": key.base_commit}

        headers = {
            "Accept": "application/vnd.github+json"
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()

        data = r.json()
        return base64.b64decode(data["content"]).decode("utf-8")
    
    def get_file_content(self, key: File, token = None):
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        content = self._get_file_content(key, token)
        self.cache.put(key, content)
        return content
    
    def put_file_content(self, key: File, content):
        self.cache.put(key, content)