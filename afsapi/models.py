"""Data models for Frontier Silicon API responses including enums and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class PlayState(IntEnum):
    """Enumeration of playback states."""

    IDLE = 0
    BUFFERING = 1
    PLAYING = 2
    PAUSED = 3
    REBUFFERING = 4
    ERROR = 5
    STOPPED = 6
    ERROR_POPUP = 7

    LOADING = BUFFERING


class PlayRepeatMode(IntEnum):
    """Enumeration of repeat modes."""

    OFF = 0
    REPEAT_ALL = 1
    REPEAT_ONE = 2


class PlayControl(IntEnum):
    """Enumeration of playback control commands."""

    STOP = 0
    PLAY = 1
    PAUSE = 2
    NEXT = 3
    """Media Player: next item in playlist (wraps around to begin of playlist).
    Radio: Next available radio on higher frequency.
    """
    PREV = 4
    """Media Player: previous item in playlist (wraps around to end of playlist).
    Radio: Next available radio on lower frequency.
    """


@dataclass
class PlayerMode:
    """Information about a player mode supported by the device."""

    id: str
    label: str
    key: int
    selectable: int | None = None
    streamable: int | None = None
    modeType: int | None = None  # noqa: N815 reflects API field name

    @property
    def modetype(self) -> int | None:  # for backwards compatibility
        """Alias for modeType field."""
        return self.modeType


@dataclass
class Equaliser:
    """Information about an equaliser preset supported by the device."""

    key: int
    label: str


@dataclass
class Preset:
    """Information about a saved preset."""

    key: int
    type: str | None = None
    name: str | None = None
