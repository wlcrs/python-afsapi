"""Recorded write integration tests against the real Frontier Silicon device."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from afsapi.exceptions import OutOfRangeError

if TYPE_CHECKING:
    from afsapi.api import AFSAPI

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.device,
]


@pytest.mark.vcr
async def test_set_power_roundtrip(device_api: AFSAPI) -> None:
    """Record power write call and restore original state."""
    original = await device_api.get_power()
    target = not original if original is not None else True

    result = await device_api.set_power(target)
    assert result in {True, False, None}

    try:
        current = await device_api.get_power()
        assert current is None or isinstance(current, bool)
    finally:
        if original is not None and original != target:
            await device_api.set_power(original)


@pytest.mark.vcr
async def test_set_volume_roundtrip(device_api: AFSAPI) -> None:
    """Record volume write call and restore original state."""
    original = await device_api.get_volume()
    volume_steps = await device_api.get_volume_steps()

    if original is None or volume_steps is None:
        pytest.skip("Volume endpoints unavailable on this device")

    if volume_steps <= 1:
        pytest.skip("Device does not expose a mutable volume range")

    target = original + 1 if original < (volume_steps - 1) else original - 1

    result = await device_api.set_volume(target)
    assert result in {True, False, None}

    try:
        current = await device_api.get_volume()
        assert current is None or isinstance(current, int)
    finally:
        if original != target:
            await device_api.set_volume(original)


@pytest.mark.vcr
async def test_set_mute_roundtrip(device_api: AFSAPI) -> None:
    """Record mute write call and restore original state."""
    original = await device_api.get_mute()
    target = not original if original is not None else True

    result = await device_api.set_mute(target)
    assert result in {True, False, None}

    try:
        current = await device_api.get_mute()
        assert current is None or isinstance(current, bool)
    finally:
        if original is not None and original != target:
            await device_api.set_mute(original)


@pytest.mark.vcr
async def test_set_sleep_roundtrip(device_api: AFSAPI) -> None:
    """Record sleep write call and restore original value when available."""
    original = await device_api.get_sleep()
    target = 10

    result = await device_api.set_sleep(target)
    assert result in {True, False, None}

    try:
        current = await device_api.get_sleep()
        assert current is None or isinstance(current, int)
    finally:
        if original is not None:
            await device_api.set_sleep(original)


@pytest.mark.vcr
async def test_play_control_commands(device_api: AFSAPI) -> None:
    """Record play-control write calls from async_tests.py."""
    play_result = await device_api.play()

    try:
        forward_result = await device_api.forward()
    except OutOfRangeError:
        forward_result = None

    try:
        rewind_result = await device_api.rewind()
    except OutOfRangeError:
        rewind_result = None

    assert play_result in {True, False, None}
    assert forward_result in {True, False, None}
    assert rewind_result in {True, False, None}
