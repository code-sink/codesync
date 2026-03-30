import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class ActivityFeed:
    def __init__(self):
        # sub_key ("owner/repo:branch")
        self.subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, sub_key: str) -> asyncio.Queue:
        # Register a new webapp client watching this repo. Returns their queue.
        queue = asyncio.Queue()
        self.subscribers[sub_key].append(queue)
        logger.info(f"ActivityFeed: new subscriber for {repo_key}, total={len(self.subscribers[repo_key])}")
        return queue

    def unsubscribe(self, sub_key: str, queue: asyncio.Queue):
        # Remove a webapp client when their SSE connection closes.
        try:
            self.subscribers[sub_key].remove(queue)
            logger.info(f"ActivityFeed: subscriber removed for {repo_key}, total={len(self.subscribers[repo_key])}")
        except ValueError:
            pass

    async def publish(self, sub_key: str, data: dict):
        # Push a snapshot to all webapp clients watching this repo.
        queues = self.subscribers.get(sub_key, [])
        if not queues:
            return
        for queue in queues:
            await queue.put(data)
        logger.info(f"ActivityFeed: published to {len(queues)} subscriber(s) for {repo_key}")

    def has_subscribers(self, sub_key: str) -> bool:
        return len(self.subscribers.get(sub_key, [])) > 0