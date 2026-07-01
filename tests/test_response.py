"""Tests for FSAPI response parsing and status handling."""

import typing as t

import pytest
from afsapi.exceptions import (
    FSApiError,
    FSNodeBlockedError,
    FSNotImplementedError,
    OutOfRangeError,
)
from afsapi.response import FSAPIStatus


@pytest.mark.parametrize(
    "status",
    [FSAPIStatus.FS_OK, FSAPIStatus.FS_LIST_END],
)
def test_to_exception_success_raises_value_error(status: FSAPIStatus) -> None:
    """Test that successful statuses raise ValueError."""
    with pytest.raises(ValueError, match="Cannot convert successful status to exception"):
        status.to_exception()


@pytest.mark.parametrize(
    ("status", "expected_exception_type", "expected_message"),
    [
        (
            FSAPIStatus.FS_NODE_DOES_NOT_EXIST,
            FSNotImplementedError,
            "FSAPI service not implemented on this device.",
        ),
        (
            FSAPIStatus.FS_NODE_BLOCKED,
            FSNodeBlockedError,
            "Device is not in the correct mode",
        ),
        (
            FSAPIStatus.FS_FAIL,
            OutOfRangeError,
            "Command failed. Value is not in range for this command.",
        ),
        (
            FSAPIStatus.FS_PACKET_BAD,
            FSApiError,
            "This command can't be SET",
        ),
    ],
)
def test_to_exception_returns_specific_exception(
    status: FSAPIStatus,
    expected_exception_type: type[FSApiError],
    expected_message: str,
) -> None:
    """Test that specific error statuses return the correct exception."""
    exc = status.to_exception()
    assert isinstance(exc, expected_exception_type)
    assert str(exc) == expected_message


def test_to_exception_unexpected_status() -> None:
    """Test that an unexpected status returns a generic FSApiError."""
    # To test the fallback of `to_exception`, we need an instance of FSAPIStatus.
    # However, Python's Enum prevents arbitrary instantiation of non-existent members.
    # But we can patch `value` and bypass identity checks by making a real Enum member
    # behave like an unexpected one.

    # Alternatively, create a mock subclass of Enum or simple mock that overrides `__eq__` properly.
    class MockStatus:
        is_success = False
        value = "FS_UNKNOWN"

        def __eq__(self, other: object) -> bool:
            return False

        def __hash__(self) -> int:
            return hash(self.value)

    exc = FSAPIStatus.to_exception(t.cast("FSAPIStatus", MockStatus()))
    assert isinstance(exc, FSApiError)
    assert type(exc) is FSApiError
    assert str(exc) == "Unexpected FSAPI status 'FS_UNKNOWN'"
