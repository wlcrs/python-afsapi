"""Unit tests for the afsapi.utils module."""

import xml.etree.ElementTree as ET

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
    # The xml.etree.ElementTree.Element always has a 'text' attribute.
    # To test the 'hasattr' safety check, we need to create a subclass of Element
    # that overrides `find` to return a mock element without a 'text' attribute,
    # since we cannot mock `find` directly on a native C-extension Element object.
    class MockRootElement(ET.Element):
        def find(self, path: str, namespaces: dict[str, str] | None = None) -> ET.Element | None:
            if path == "key":
                class NoTextElement:
                    pass
                return NoTextElement()  # type: ignore[return-value]
            return super().find(path, namespaces)

    root = MockRootElement("root")

    assert unpack_xml(root, "key") is None


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
    # Defusedxml or other parsers might occasionally return non-string content (e.g. CDATA types)
    # The standard ElementTree text setter expects str or None, so we assign via setattr
    root = ET.Element("root")
    child = ET.SubElement(root, "key")
    child.text = 123  # type: ignore[assignment]

    assert unpack_xml(root, "key") == "123"
