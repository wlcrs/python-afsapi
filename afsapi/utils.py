"""Utility functions for XML parsing and type transformation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    from defusedxml import ElementTree


def unpack_xml(root: ElementTree.Element | None, key: str) -> str | None:
    """Extract text content from an XML element.

    Args:
        root: The root XML element to search within, or None.
        key: The tag name to search for.

    Returns:
        The text content of the element, or None if not found.

    """
    if root:
        element = root.find(key)

        if element is not None and hasattr(element, "text") and element.text is not None:
            return str(element.text)

    return None


A = TypeVar("A")
B = TypeVar("B")


def maybe(
    val: A | None,
    fn: Callable[[A], B] | type[B],
) -> B | None:
    """Apply a function to a value if it is not None.

    Args:
        val: The value to conditionally transform.
        fn: A callable or type to apply to the value.

    Returns:
        The result of applying fn, or None if val is None.

    """
    if val is not None:
        return fn(val)  # type: ignore[call-arg]
    return None
