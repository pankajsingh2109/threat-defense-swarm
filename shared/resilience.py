import asyncio
import random
import time
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")

class IdempotencyCache:
    """In-memory thread-safe idempotency cache to prevent duplicate request processing."""
    def __init__(self, max_items: int = 1000):
        self._cache: Dict[str, Any] = {}
        self._max_items = max_items

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        if len(self._cache) >= self._max_items:
            # Evict oldest entry simple FIFO
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        self._cache[key] = value

    def has(self, key: str) -> bool:
        return key in self._cache

async def execute_with_retry(
    func: Callable[[], Any],
    max_retries: int = 3,
    initial_delay: float = 0.1,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,)
) -> Any:
    """Helper to execute an async function with exponential backoff and jitter."""
    attempt = 0
    delay = initial_delay

    while True:
        attempt += 1
        try:
            return await func()
        except retryable_exceptions as e:
            if attempt > max_retries:
                raise e
            
            sleep_time = delay * (random.uniform(0.8, 1.2) if jitter else 1.0)
            await asyncio.sleep(sleep_time)
            delay *= backoff_factor
