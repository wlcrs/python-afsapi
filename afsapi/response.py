"""XML response parsing and status handling for FSAPI.

This module provides parsing utilities for Frontier Silicon API XML responses,
including status code handling, field extraction, and response marshalling.
"""

from __future__ import annotations

import typing as t
from dataclasses import dataclass
from enum import Enum

if t.TYPE_CHECKING:
    from defusedxml import ElementTree

from afsapi.exceptions import (
    FSApiError,
    FsNotImplementedError,
    OutOfRangeError,
)


class FSAPIStatus(Enum):
    """FSAPI response status codes.

    Represents the possible status codes returned by Frontier Silicon devices
    in XML responses, mapping to their string representations.
    """

    FS_OK = "FS_OK"
    """Request completed successfully."""

    FS_LIST_END = "FS_LIST_END"
    """Navigation reached the end of a list."""

    FS_NODE_DOES_NOT_EXIST = "FS_NODE_DOES_NOT_EXIST"
    """The requested node is not available on the device."""

    FS_NODE_BLOCKED = "FS_NODE_BLOCKED"
    """Device is not in the correct mode for this operation."""

    FS_FAIL = "FS_FAIL"
    """Command failed, possibly due to invalid parameters or out-of-range value."""

    FS_PACKET_BAD = "FS_PACKET_BAD"
    """Cannot SET on a read-only node."""

    @property
    def is_success(self) -> bool:
        """Return True if status indicates successful operation.

        Returns:
            True if status is FS_OK or FS_LIST_END.

        """
        return self in {FSAPIStatus.FS_OK, FSAPIStatus.FS_LIST_END}

    def to_exception(self) -> FSApiError | None:
        """Convert non-success status to corresponding exception.

        Returns:
            An exception instance for non-success statuses, or None if successful.

        """
        if self.is_success:
            return None

        if self == FSAPIStatus.FS_NODE_DOES_NOT_EXIST:
            msg = "FSAPI service not implemented on this device."
            return FsNotImplementedError(msg)
        if self == FSAPIStatus.FS_NODE_BLOCKED:
            msg = "Device is not in the correct mode"
            return FSApiError(msg)
        if self == FSAPIStatus.FS_FAIL:
            msg = "Command failed. Value is not in range for this command."
            return OutOfRangeError(msg)
        if self == FSAPIStatus.FS_PACKET_BAD:
            msg = "This command can't be SET"
            return FSApiError(msg)

        msg = f"Unexpected FSAPI status '{self.value}'"
        return FSApiError(msg)


@dataclass(frozen=True)
class FSAPIResponse:
    """Parsed FSAPI XML response.

    Encapsulates the status and data from an FSAPI response.

    Attributes:
        status: The FSAPI status code.
        data: The parsed response data (typically an ElementTree.Element
            containing the response value).

    """

    status: FSAPIStatus
    data: t.Any = None

    @property
    def is_success(self) -> bool:
        """Return True if response indicates success.

        Returns:
            True if status is successful (FS_OK or FS_LIST_END).

        """
        return self.status.is_success


def parse_status(
    root: ElementTree.Element | None,
) -> FSAPIStatus:
    """Extract and parse FSAPI status from XML response.

    Args:
        root: The root XML element from the response, or None.

    Returns:
        The parsed status code, or FS_FAIL if not found.

    """
    if root is None:
        return FSAPIStatus.FS_FAIL

    status_elem = root.find("status")
    if status_elem is None or status_elem.text is None:
        return FSAPIStatus.FS_FAIL

    status_text = status_elem.text.strip()
    try:
        return FSAPIStatus(status_text)
    except ValueError:
        return FSAPIStatus.FS_FAIL


def parse_response(
    root: ElementTree.Element | None,
) -> FSAPIResponse:
    """Parse complete FSAPI XML response.

    Extracts status from the response, validates it, and returns a structured
    response object. If status indicates failure, raises appropriate exception.

    Args:
        root: The root XML element from the response.

    Returns:
        Parsed response with status and data.

    Raises:
        FsNotImplementedError: If node is not implemented.
        FSApiError: If status indicates failure.
        OutOfRangeError: If value is out of valid range.

    """
    status = parse_status(root)

    if not status.is_success:
        exception = status.to_exception()
        if exception:
            raise exception

    return FSAPIResponse(status=status, data=root)


def extract_text(
    root: ElementTree.Element | None,
    *path: str,
) -> str | None:
    """Extract text from nested XML element.

    Navigates the XML tree using the provided path elements and returns
    the text content of the final element.

    Args:
        root: The root XML element to start from, or None.
        *path: Variable-length path elements (tag names) to navigate.

    Returns:
        The text content of the element, or None if not found or empty.

    Example:
        >>> extract_text(root, "value", "c8_array")

    """
    if root is None:
        return None

    current = root
    for tag in path:
        current = current.find(tag)
        if current is None:
            return None

    if current.text is None:
        return None

    text = current.text.strip()
    return text or None


def extract_list_items(
    root: ElementTree.Element | None,
) -> list[ElementTree.Element]:
    """Extract all item elements from list response.

    Args:
        root: The root XML element containing list items, or None.

    Returns:
        List of item elements, or empty list if not found.

    """
    if root is None:
        return []

    return root.findall("item")


def extract_item_key(
    item: ElementTree.Element,
    default: int = -1,
) -> int:
    """Extract key attribute from list item element.

    Args:
        item: The item element.
        default: Default value if key is missing or invalid.

    Returns:
        The item key as integer, or default if not found.

    """
    key_str = item.attrib.get("key")
    if key_str is None:
        return default

    try:
        return int(key_str)
    except (ValueError, TypeError):
        return default


def extract_item_fields(
    item: ElementTree.Element,
) -> dict[str, tuple[str, str]]:
    """Extract all field elements from list item.

    Parses field elements and returns a mapping of field names to
    (tag_name, text_value) tuples, allowing callers to handle type conversion.

    Args:
        item: The item element containing field children.

    Returns:
        Dictionary mapping field name to (tag, value) tuple.
        Empty dict if no fields found.

    Example:
        >>> fields = extract_item_fields(item)
        >>> for name, (tag, value) in fields.items():
        ...     print(f"{name}: {tag}={value}")

    """
    fields = {}
    for field_elem in item.findall("field"):
        name = field_elem.attrib.get("name")
        if name is None:
            continue

        if len(field_elem) == 0 or field_elem[0].text is None:
            continue

        tag = field_elem[0].tag
        text = field_elem[0].text.strip()
        if text:
            fields[name] = (tag, text)

    return fields
