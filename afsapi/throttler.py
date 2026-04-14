"""Rate throttling context manager for controlling request execution frequency."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# pylint: disable-next=too-few-public-methods
class Throttler:
    """Ensures that a time between executions is taken into account for each wrapped code block.

    This can be configured for every throttle call.
    """

    def __init__(self) -> None:
        """Initialize the Throttler."""
        self._lock = asyncio.Lock()
        self._next_execution_not_before: float | None = None

    @asynccontextmanager
    async def throttle(self, throttle_after_call_s: float) -> AsyncGenerator[None, None]:
        """Create a throttle context manager for rate limiting.

        Args:
            throttle_after_call_s: Seconds to wait after exiting the context.

        Yields:
            None

        """
        await self._lock.acquire()
        try:
            if self._next_execution_not_before is not None:
                additional_wait = self._next_execution_not_before - time.monotonic()

                if additional_wait > 0:
                    await asyncio.sleep(additional_wait)
            yield
        finally:
            self._next_execution_not_before = time.monotonic() + throttle_after_call_s
            self._lock.release()
