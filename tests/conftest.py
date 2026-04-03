"""Pytest configuration for integration tests against a real Frontier Silicon device."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from afsapi.api import AFSAPI

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

DEFAULT_DEVICE_IP = "192.168.1.183"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options."""
    parser.addoption(
        "--run-device-tests",
        action="store_true",
        default=False,
        help="Run integration tests against the physical FSAPI device.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Configure device tests for replay-by-default behavior.

    - Default: run device tests from existing cassettes only.
    - With ``--run-device-tests``: allow live device access/recording.
    """
    if config.getoption("--run-device-tests"):
        return

    for item in items:
        if "device" in item.keywords:
            item.add_marker(pytest.mark.vcr(record_mode="none"))


@pytest.fixture
def device_pin(pytestconfig: pytest.Config) -> str:
    """Return the device pin from environment.

    In replay mode, a placeholder pin is sufficient because requests are served
    from recorded cassettes with filtered query parameters.
    """
    pin = os.getenv("AFSAPI_DEVICE_PIN")
    if pytestconfig.getoption("--run-device-tests") and not pin:
        pytest.skip("Set AFSAPI_DEVICE_PIN to run device integration tests")
    return pin or "0000"


@pytest.fixture
def device_ip(pytestconfig: pytest.Config) -> str:
    """Return the radio IP from environment.

    In replay mode, defaults to the cassette host.
    In live mode, the env var is required.
    """
    ip = os.getenv("AFSAPI_DEVICE_IP")
    if pytestconfig.getoption("--run-device-tests") and not ip:
        pytest.skip("Set AFSAPI_DEVICE_IP to run device integration tests")
    return ip or DEFAULT_DEVICE_IP


@pytest.fixture
def vcr_config() -> dict[str, object]:
    """Configure pytest-recording cassettes.

    Sensitive query params are filtered from recorded URLs.
    """
    return {
        "filter_query_parameters": [
            ("pin", "PIN"),
            ("sid", "SID"),
        ],
        "decode_compressed_response": True,
    }


@pytest_asyncio.fixture
async def device_api(device_pin: str, device_ip: str) -> AsyncGenerator[AFSAPI]:
    """Yield an initialized API client bound to the development device."""
    api = AFSAPI(f"http://{device_ip}/fsapi", device_pin)
    try:
        yield api
    finally:
        await api.close()
