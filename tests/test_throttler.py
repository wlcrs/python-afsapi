"""Tests for the Throttler class."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from afsapi.throttler import Throttler


@pytest.mark.asyncio
async def test_throttler_first_call_no_sleep() -> None:
    """Test that the first call to throttle does not sleep."""
    throttler = Throttler()

    mock_time = 100.0
    expected_next_execution = 101.0

    with (
        patch("afsapi.throttler.time.monotonic", return_value=mock_time),
        patch("afsapi.throttler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        async with throttler.throttle(1.0):
            pass

        mock_sleep.assert_not_called()
        assert throttler._next_execution_not_before == expected_next_execution  # noqa: SLF001


@pytest.mark.asyncio
async def test_throttler_subsequent_call_sleeps() -> None:
    """Test that subsequent calls wait the appropriate amount of time."""
    throttler = Throttler()

    mock_time_1 = 100.0
    mock_time_2 = 105.0
    throttle_time = 2.0
    expected_sleep = 5.0
    expected_next_execution = 107.0

    # Simulate that a call has already happened, and next execution should not be before 105.0
    throttler._next_execution_not_before = mock_time_2  # noqa: SLF001

    with (
        patch("afsapi.throttler.time.monotonic", side_effect=[mock_time_1, mock_time_2]),
        patch("afsapi.throttler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        async with throttler.throttle(throttle_time):
            pass

        mock_sleep.assert_called_once_with(expected_sleep)
        assert throttler._next_execution_not_before == expected_next_execution  # noqa: SLF001


@pytest.mark.asyncio
async def test_throttler_no_wait_if_time_passed() -> None:
    """Test that no sleep occurs if the required time has already passed."""
    throttler = Throttler()

    mock_time = 105.0
    past_time = 100.0
    throttle_time = 2.0
    expected_next_execution = 107.0

    throttler._next_execution_not_before = past_time  # noqa: SLF001

    with (
        patch("afsapi.throttler.time.monotonic", return_value=mock_time),
        patch("afsapi.throttler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        async with throttler.throttle(throttle_time):
            pass

        mock_sleep.assert_not_called()
        assert throttler._next_execution_not_before == expected_next_execution  # noqa: SLF001


@pytest.mark.asyncio
async def test_throttler_concurrent_calls() -> None:
    """Test that concurrent calls to throttle acquire the lock sequentially.

    Using a very small sleep to ensure fast execution while proving the logic.
    """
    throttler = Throttler()
    execution_order = []

    num_workers = 3
    throttle_time = 0.05
    minimum_expected_time = 0.08

    async def worker(worker_id: int) -> None:
        async with throttler.throttle(throttle_time):
            execution_order.append(worker_id)

    start_time = time.monotonic()

    # Run 3 workers concurrently
    await asyncio.gather(worker(1), worker(2), worker(3))

    end_time = time.monotonic()

    # All workers should have executed
    assert len(execution_order) == num_workers

    # 3 workers with 0.05s throttle between them.
    # Worker 1: 0s wait
    # Worker 2: ~0.05s wait
    # Worker 3: ~0.10s wait
    # Total time should be at least ~0.10s (allow some margin for timing inaccuracy, so > 0.08)
    assert (end_time - start_time) >= minimum_expected_time
