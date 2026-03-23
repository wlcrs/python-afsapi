"""Integration tests recorded from a real Frontier Silicon device."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from afsapi.models import Equaliser, PlayerMode, PlayState, Preset

if TYPE_CHECKING:
    from afsapi.api import AFSAPI

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.device,
]


@pytest.mark.vcr
async def test_known_fsapi_endpoint_responds(device_api: AFSAPI) -> None:
    """Record a basic call against the known /fsapi endpoint."""
    friendly_name = await device_api.get_friendly_name()
    assert friendly_name is None or isinstance(friendly_name, str)


@pytest.mark.vcr
async def test_get_friendly_name(device_api: AFSAPI) -> None:
    """Record friendly name read call."""
    friendly_name = await device_api.get_friendly_name()
    assert friendly_name is None or isinstance(friendly_name, str)


@pytest.mark.vcr
async def test_get_power(device_api: AFSAPI) -> None:
    """Record power state read call."""
    power = await device_api.get_power()
    assert power is None or isinstance(power, bool)


@pytest.mark.vcr
async def test_get_volume(device_api: AFSAPI) -> None:
    """Record volume read call."""
    volume = await device_api.get_volume()
    assert volume is None or isinstance(volume, int)


@pytest.mark.vcr
async def test_get_play_status(device_api: AFSAPI) -> None:
    """Record play status read call."""
    status = await device_api.get_play_status()
    assert status is None or isinstance(status, PlayState)


@pytest.mark.vcr
async def test_get_modes(device_api: AFSAPI) -> None:
    """Record supported modes list call."""
    modes = await device_api.get_modes()
    assert isinstance(modes, list)
    assert all(isinstance(mode, PlayerMode) for mode in modes)


@pytest.mark.vcr
async def test_get_equalisers(device_api: AFSAPI) -> None:
    """Record equaliser list call."""
    equalisers = await device_api.get_equalisers()
    assert isinstance(equalisers, list)
    assert all(isinstance(equaliser, Equaliser) for equaliser in equalisers)


@pytest.mark.vcr
async def test_get_eq_preset(device_api: AFSAPI) -> None:
    """Record current equaliser preset call."""
    eq_preset = await device_api.get_eq_preset()
    assert eq_preset is None or isinstance(eq_preset, Equaliser)


@pytest.mark.vcr
async def test_get_presets(device_api: AFSAPI) -> None:
    """Record presets list call."""
    presets = await device_api.get_presets()
    assert isinstance(presets, list)
    assert all(isinstance(preset, Preset) for preset in presets)


@pytest.mark.vcr
async def test_info_endpoints(device_api: AFSAPI) -> None:
    """Record various informational endpoint reads from async_tests.py."""
    radio_id = await device_api.get_radio_id()
    version = await device_api.get_version()
    mac = await device_api.get_mac()
    rssi = await device_api.get_rssi()

    assert radio_id is None or isinstance(radio_id, str)
    assert version is None or isinstance(version, str)
    assert mac is None or isinstance(mac, str)
    assert rssi is None or isinstance(rssi, int)


@pytest.mark.vcr
async def test_play_info_endpoints(device_api: AFSAPI) -> None:
    """Record currently playing metadata reads from async_tests.py."""
    name = await device_api.get_play_name()
    text = await device_api.get_play_text()
    artist = await device_api.get_play_artist()
    album = await device_api.get_play_album()
    graphic = await device_api.get_play_graphic()
    duration = await device_api.get_play_duration()

    assert name is None or isinstance(name, str)
    assert text is None or isinstance(text, str)
    assert artist is None or isinstance(artist, str)
    assert album is None or isinstance(album, str)
    assert graphic is None or isinstance(graphic, str)
    assert duration is None or isinstance(duration, int)


@pytest.mark.vcr
async def test_get_sleep(device_api: AFSAPI) -> None:
    """Record sleep-timer read call."""
    sleep = await device_api.get_sleep()
    assert sleep is None or isinstance(sleep, int)
