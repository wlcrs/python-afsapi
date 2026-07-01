"""Unit tests for the afsapi.utils module."""

import xml.etree.ElementTree as ET
from unittest.mock import Mock

from afsapi.utils import unpack_xml


def test_unpack_xml_root_is_none() -> None:
    """Test that unpack_xml returns None when root is None."""
    assert unpack_xml(None, "key") is None


def test_unpack_xml_key_not_found() -> None:
    """Test that unpack_xml returns None when key is not found."""
    root = ET.Element("root")
    assert unpack_xml(root, "missing_key") is None


def test_unpack_xml_element_has_no_text_attribute() -> None:
    """Test that unpack_xml returns None when element lacks 'text' attribute."""
    # Create a mock element that doesn't have a 'text' attribute
    mock_root = Mock()
    mock_element = object()  # Object without a 'text' attribute
    mock_root.find.return_value = mock_element

    assert unpack_xml(mock_root, "key") is None


def test_unpack_xml_element_text_is_none() -> None:
    """Test that unpack_xml returns None when element.text is None."""
    root = ET.Element("root")
    child = ET.SubElement(root, "key")
    child.text = None

    assert unpack_xml(root, "key") is None


def test_unpack_xml_success() -> None:
    """Test that unpack_xml returns the correct text when key is found."""
    root = ET.Element("root")
    child = ET.SubElement(root, "key")
    child.text = "expected text"

    assert unpack_xml(root, "key") == "expected text"


def test_unpack_xml_numeric_text() -> None:
    """Test that unpack_xml casts non-string text to string."""
    # Some XML libraries or specific mock implementations might set text to non-string
    mock_root = Mock()
    mock_child = Mock()
    mock_child.text = 123
    mock_root.find.return_value = mock_child

    assert unpack_xml(mock_root, "key") == "123"
