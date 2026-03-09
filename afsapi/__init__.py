"""Asynchronous implementation of the Frontier Silicon API."""

from importlib.metadata import PackageNotFoundError, version

from afsapi.exceptions import (
    FSApiError,
    FSConnectionError,
    FsNotImplementedError,
    InvalidPinError,
    InvalidSessionError,
    OutOfRangeError,
)
from afsapi.models import (
    Equaliser,
    PlayControl,
    PlayerMode,
    PlayRepeatMode,
    PlayState,
    Preset,
)

from .api import AFSAPI

try:
    VERSION = version(__name__)
except PackageNotFoundError:  # pragma: no cover
    try:
        from .version import __version__ as VERSION
    except ImportError:  # pragma: no cover
        VERSION = "0.0.0.dev0"
__version__ = VERSION

__all__ = [
    "AFSAPI",
    "Equaliser",
    "FSApiError",
    "FSConnectionError",
    "FsNotImplementedError",
    "InvalidPinError",
    "InvalidSessionError",
    "OutOfRangeError",
    "PlayControl",
    "PlayRepeatMode",
    "PlayState",
    "PlayerMode",
    "Preset",
]
