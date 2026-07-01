"""Tests for afsapi.response module."""

import xml.etree.ElementTree as ET

from afsapi.response import extract_item_key


def test_extract_item_key_valid() -> None:
    """Test extracting a valid integer key."""
    expected = 42
    item = ET.Element("item", {"key": "42"})
    assert extract_item_key(item) == expected


def test_extract_item_key_default() -> None:
    """Test extracting a missing key uses the default."""
    expected = 10
    item = ET.Element("item")
    assert extract_item_key(item) == -1
    assert extract_item_key(item, default=expected) == expected


def test_extract_item_key_value_error() -> None:
    """Test extracting a non-integer key string returns the default."""
    expected = 99
    item = ET.Element("item", {"key": "not-an-int"})
    assert extract_item_key(item) == -1
    assert extract_item_key(item, default=expected) == expected


def test_extract_item_key_type_error() -> None:
    """Test extracting an invalid type for key returns the default.

    We pass a type that is not None and not convertible to int,
    so it hits the except TypeError block.
    """
    expected = 77
    item = ET.Element("item")
    item.attrib["key"] = object()  # type: ignore[assignment]
    assert extract_item_key(item) == -1
    assert extract_item_key(item, default=expected) == expected
