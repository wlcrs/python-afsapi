"""Test of the asynchronous Frontier Silicon interface."""

import asyncio
import logging
import traceback

from afsapi import AFSAPI

logger = logging.getLogger(__name__)

URL = "http://192.168.1.183:80/device"
PIN = 1234
TIMEOUT = 2  # in seconds


async def test_sys() -> None:
    """Test sys functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)

        for _mode in await afsapi.get_modes():
            pass

        for _equaliser in await afsapi.get_equalisers():
            pass

        for _preset in await afsapi.get_presets():
            pass

    except Exception:
        logger.exception(traceback.format_exc())


async def test_volume() -> None:
    """Test volume functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)

        await afsapi.set_power(True)

        await afsapi.get_power()

        await afsapi.get_volume()

        await afsapi.set_volume(3)

        await afsapi.get_volume_steps()

        await afsapi.get_mute()

        await afsapi.set_power(False)

        await afsapi.get_power()
    except Exception:
        logger.exception(traceback.format_exc())


async def test_info() -> None:
    """Test info functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)

        await afsapi.set_power(True)

        await afsapi.get_power()

        await afsapi.get_play_name()

        await afsapi.get_play_text()

        await afsapi.get_play_artist()

        await afsapi.get_play_album()

        await afsapi.get_play_graphic()

        await afsapi.get_play_duration()

        power = await afsapi.set_power(False)
        print(f"Set power succeeded? - {power}")

        power = await afsapi.get_power()
        print(f"Power on: {power}")
    except Exception:
        logger.exception(traceback.format_exc())


async def test_play() -> None:
    """Test play functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)

        await afsapi.get_play_status()

        await afsapi.play()
        await asyncio.sleep(1)

        await afsapi.forward()
        await asyncio.sleep(1)

        await afsapi.rewind()

    except Exception:
        logger.exception(traceback.format_exc())


loop = asyncio.new_event_loop()

loop.run_until_complete(test_sys())
loop.run_until_complete(test_volume())
loop.run_until_complete(test_play())
loop.run_until_complete(test_info())
