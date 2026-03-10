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
from afsapi.nodes import (
    Endpoint,
    ListEndpoint,
    Nodes,
)

from .api import AFSAPI

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # pragma: no cover
    try:
        from .version import __version__
    except ImportError:  # pragma: no cover
        __version__ = "0.0.0.dev0"

__all__ = [
    "AFSAPI",
    "Endpoint",
    "Equaliser",
    "FSApiError",
    "FSConnectionError",
    "FsNotImplementedError",
    "InvalidPinError",
    "InvalidSessionError",
    "ListEndpoint",
    "Nodes",
    "OutOfRangeError",
    "PlayControl",
    "PlayRepeatMode",
    "PlayState",
    "PlayerMode",
    "Preset",
]
