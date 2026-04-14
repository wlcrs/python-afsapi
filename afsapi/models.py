"""Data models for Frontier Silicon API responses including enums and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag, auto


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


class PlayCaps(IntFlag):
    """Bitmask of supported playback control commands.

    Returned by netRemote.play.caps endpoint.
    """

    PAUSE = auto()
    STOP = auto()
    SKIP_NEXT = auto()
    SKIP_PREVIOUS = auto()
    FAST_FORWARD = auto()
    REWIND = auto()
    SHUFFLE = auto()
    REPEAT = auto()
    SEEK = auto()
    APPLY_FEEDBACK = auto()
    SCROBBLING = auto()
    ADD_PRESET = auto()
    THUMBS_UP = auto()
    THUMBS_DOWN = auto()
    SKIP_FORWARD = auto()
    SKIP_BACKWARD = auto()
    REPEAT_ONE = auto()


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
    modetype: int | None = None


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
