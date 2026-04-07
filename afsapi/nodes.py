"""Typed FSAPI node definitions.

Inspired by fsapi-tools' APICall[_T] pattern, this module defines typed endpoint
descriptors that encode expected return types at the class level. This allows a
single generic ``get()`` method on the API client to return properly typed values
without runtime type dispatch by the caller.

Each endpoint is declared as either:

- ``Endpoint[T](path, xml_tag)`` for scalar values (str, int)
- ``ListEndpoint[T](path)`` for list values yielding TypedDict items

Example usage with the API client::

    name = await api.get(Nodes.friendly_name)   # inferred: str | None
    vol  = await api.get(Nodes.volume)           # inferred: int | None
    eqs  = await api.get(Nodes.equalisers)       # inferred: AsyncIterable[...]
"""

from __future__ import annotations

import typing as t
from typing import TypedDict

# ---------------------------------------------------------------------------
# Generic endpoint descriptors
# ---------------------------------------------------------------------------

_T = t.TypeVar("_T")

# XML tags that represent string values (returned as-is)
_STRING_TAGS: frozenset[str] = frozenset({"c8_array"})


class Endpoint(t.Generic[_T]):
    """Typed FSAPI scalar endpoint.

    Encodes both the netRemote path and the XML tag used to extract the value.
    The generic parameter ``_T`` tells the type checker what Python type to
    expect from the ``get()`` method.

    Args:
        path: The netRemote endpoint path (e.g. ``netRemote.sys.audio.volume``).
        xml_tag: The XML element tag that wraps the value
                 (e.g. ``u8``, ``u32``, ``c8_array``).

    """

    __slots__ = ("path", "xml_tag")

    def __init__(self, path: str, xml_tag: str) -> None:
        """Initialise with a netRemote path and XML value tag."""
        self.path = path
        self.xml_tag = xml_tag

    @property
    def is_string_type(self) -> bool:
        """Return True if this endpoint carries a string value."""
        return self.xml_tag in _STRING_TAGS

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"Endpoint[{self.xml_tag}]({self.path!r})"


class ListEndpoint(t.Generic[_T]):
    """Typed FSAPI list endpoint.

    The generic parameter ``_T`` is the TypedDict describing each list item's
    fields.  At runtime the list handler iterates the XML ``<item>`` elements
    and returns parsed dicts.

    Args:
        path: The netRemote endpoint path (e.g. ``netRemote.nav.list``).

    """

    __slots__ = ("path",)

    def __init__(self, path: str) -> None:
        """Initialise with a netRemote list path."""
        self.path = path

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"ListEndpoint({self.path!r})"


# ---------------------------------------------------------------------------
# List-item TypedDicts — based on fsapi-tools node prototypes
# ---------------------------------------------------------------------------


class EqualisersListItem(TypedDict):
    """EQ Preset list item from ``netRemote.sys.caps.eqPresets``."""

    key: int
    label: str


class ValidModesListItem(TypedDict):
    """Valid modes list item from ``netRemote.sys.caps.validModes``."""

    key: int
    id: str
    selectable: int
    label: str
    streamable: int
    modeType: int


class NavListItem(TypedDict):
    """Navigation list item from ``netRemote.nav.list``."""

    key: int
    name: str
    type: int
    subType: int
    graphicUri: str
    artist: str
    contextMenu: int


class PresetsListItem(TypedDict):
    """Preset list item from ``netRemote.nav.presets``."""

    key: int
    name: str
    type: str
    uniqid: str
    blob: str
    artworkUrl: str


# ---------------------------------------------------------------------------
# Node registry — the single source of truth for every endpoint
# ---------------------------------------------------------------------------


class Nodes:
    """FSAPI node definitions with fully typed endpoints.

    Scalar endpoints use ``Endpoint[T]`` where T is the expected Python type.
    List endpoints use ``ListEndpoint[T]`` where T is the TypedDict for items.

    Access as class attributes::

        Nodes.volume        # Endpoint[int]
        Nodes.friendly_name # Endpoint[str]
        Nodes.equalisers    # ListEndpoint[EqualisersListItem]
    """

    # --- sys ---------------------------------------------------------------
    power: Endpoint[int] = Endpoint("netRemote.sys.power", "u8")
    mode: Endpoint[int] = Endpoint("netRemote.sys.mode", "u32")

    wired_mac: Endpoint[str] = Endpoint("netRemote.sys.net.wired.macAddress", "c8_array")
    wired_active: Endpoint[int] = Endpoint("netRemote.sys.net.wired.interfaceEnable", "u8")
    wlan_mac: Endpoint[str] = Endpoint("netRemote.sys.net.wlan.macAddress", "c8_array")
    wlan_active: Endpoint[int] = Endpoint("netRemote.sys.net.wlan.interfaceEnable", "u8")
    rssi: Endpoint[int] = Endpoint("netRemote.sys.net.wlan.rssi", "u8")

    # --- sys.info ----------------------------------------------------------
    friendly_name: Endpoint[str] = Endpoint("netRemote.sys.info.friendlyName", "c8_array")
    radio_id: Endpoint[str] = Endpoint("netRemote.sys.info.radioId", "c8_array")
    version: Endpoint[str] = Endpoint("netRemote.sys.info.version", "c8_array")

    # --- sys.caps ----------------------------------------------------------
    valid_modes: ListEndpoint[ValidModesListItem] = ListEndpoint("netRemote.sys.caps.validModes")
    equalisers: ListEndpoint[EqualisersListItem] = ListEndpoint("netRemote.sys.caps.eqPresets")
    sleep: Endpoint[int] = Endpoint("netRemote.sys.sleep", "u32")

    # --- sys.audio ---------------------------------------------------------
    eqpreset: Endpoint[int] = Endpoint("netRemote.sys.audio.eqPreset", "u8")
    eqloudness: Endpoint[int] = Endpoint("netRemote.sys.audio.eqLoudness", "u8")
    bass: Endpoint[int] = Endpoint("netRemote.sys.audio.eqCustom.param0", "s16")
    treble: Endpoint[int] = Endpoint("netRemote.sys.audio.eqCustom.param1", "s16")

    # --- volume ------------------------------------------------------------
    volume_steps: Endpoint[int] = Endpoint("netRemote.sys.caps.volumeSteps", "u8")
    volume: Endpoint[int] = Endpoint("netRemote.sys.audio.volume", "u8")
    mute: Endpoint[int] = Endpoint("netRemote.sys.audio.mute", "u8")

    # --- play --------------------------------------------------------------
    caps: Endpoint[int] = Endpoint("netRemote.play.caps", "u32")
    status: Endpoint[int] = Endpoint("netRemote.play.status", "u8")
    name: Endpoint[str] = Endpoint("netRemote.play.info.name", "c8_array")
    control: Endpoint[int] = Endpoint("netRemote.play.control", "u8")
    shuffle: Endpoint[int] = Endpoint("netRemote.play.shuffle", "u8")
    repeat: Endpoint[int] = Endpoint("netRemote.play.repeat", "u8")
    position: Endpoint[int] = Endpoint("netRemote.play.position", "u32")
    rate: Endpoint[int] = Endpoint("netRemote.play.rate", "s8")

    # --- play.info ---------------------------------------------------------
    text: Endpoint[str] = Endpoint("netRemote.play.info.text", "c8_array")
    artist: Endpoint[str] = Endpoint("netRemote.play.info.artist", "c8_array")
    album: Endpoint[str] = Endpoint("netRemote.play.info.album", "c8_array")
    graphic_uri: Endpoint[str] = Endpoint("netRemote.play.info.graphicUri", "c8_array")
    duration: Endpoint[int] = Endpoint("netRemote.play.info.duration", "u32")

    # --- nav ---------------------------------------------------------------
    nav_state: Endpoint[int] = Endpoint("netRemote.nav.state", "u8")
    numitems: Endpoint[int] = Endpoint("netRemote.nav.numItems", "s32")
    nav_list: ListEndpoint[NavListItem] = ListEndpoint("netRemote.nav.list")
    navigate: Endpoint[int] = Endpoint("netRemote.nav.action.navigate", "u8")
    select_item: Endpoint[int] = Endpoint("netRemote.nav.action.selectItem", "u8")
    presets: ListEndpoint[PresetsListItem] = ListEndpoint("netRemote.nav.presets")
    select_preset: Endpoint[int] = Endpoint("netRemote.nav.action.selectPreset", "u8")
