"""Test of the asynchronous Frontier Silicon interface."""

# pylint: disable=all

import asyncio
import logging

from afsapi import AFSAPI

logger = logging.getLogger(__name__)

URL = "http://192.168.1.183:80/device"
PIN = 1234
TIMEOUT = 2  # in seconds


async def test_sys() -> None:
    """Test sys functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)

        async with afsapi:
            for mode in await afsapi.get_modes():
                print(f"mode: {mode}")

            for equaliser in await afsapi.get_equalisers():
                print(f"equaliser: {equaliser}")

            for preset in await afsapi.get_presets():
                print(f"preset: {preset}")

    except Exception:
        logger.exception("An error occurred")


async def test_volume() -> None:
    """Test volume functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)
        async with afsapi:
            power_set = await afsapi.set_power(True)
            print(f"set_power(True): {power_set}")

            power = await afsapi.get_power()
            print(f"get_power: {power}")

            volume = await afsapi.get_volume()
            print(f"get_volume: {volume}")

            volume_set = await afsapi.set_volume(3)
            print(f"set_volume(3): {volume_set}")

            volume_steps = await afsapi.get_volume_steps()
            print(f"get_volume_steps: {volume_steps}")

            mute = await afsapi.get_mute()
            print(f"get_mute: {mute}")

            power_set = await afsapi.set_power(False)
            print(f"set_power(False): {power_set}")

            power = await afsapi.get_power()
            print(f"get_power: {power}")
    except Exception:
        logger.exception("An error occurred")


async def test_info() -> None:
    """Test info functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)

        async with afsapi:
            power_set = await afsapi.set_power(True)
            print(f"set_power(True): {power_set}")

            power = await afsapi.get_power()
            print(f"get_power: {power}")

            play_name = await afsapi.get_play_name()
            print(f"get_play_name: {play_name}")

            play_text = await afsapi.get_play_text()
            print(f"get_play_text: {play_text}")

            play_artist = await afsapi.get_play_artist()
            print(f"get_play_artist: {play_artist}")

            play_album = await afsapi.get_play_album()
            print(f"get_play_album: {play_album}")

            play_graphic = await afsapi.get_play_graphic()
            print(f"get_play_graphic: {play_graphic}")

            play_duration = await afsapi.get_play_duration()
            print(f"get_play_duration: {play_duration}")

            power = await afsapi.set_power(False)
            print(f"Set power succeeded? - {power}")

            power = await afsapi.get_power()
            print(f"Power on: {power}")
    except Exception:
        logger.exception("An error occurred")


async def test_play() -> None:
    """Test play functions."""
    try:
        afsapi = await AFSAPI.create(URL, PIN, TIMEOUT)
        async with afsapi:
            play_status = await afsapi.get_play_status()
            print(f"get_play_status: {play_status}")

            play_result = await afsapi.play()
            print(f"play: {play_result}")
            await asyncio.sleep(1)

            forward_result = await afsapi.forward()
            print(f"forward: {forward_result}")
            await asyncio.sleep(1)

            rewind_result = await afsapi.rewind()
            print(f"rewind: {rewind_result}")

    except Exception:
        logger.exception("An error occurred")


loop = asyncio.new_event_loop()

loop.run_until_complete(test_sys())
loop.run_until_complete(test_volume())
loop.run_until_complete(test_play())
loop.run_until_complete(test_info())
