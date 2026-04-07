"""Asynchronous implementation of the Frontier Silicon API."""

from importlib.metadata import PackageNotFoundError, version

from .api import AFSAPI
from .exceptions import (
    FSApiError,
    FSConnectionError,
    FSNotImplementedError,
    InvalidPinError,
    InvalidSessionError,
    OutOfRangeError,
)
from .models import (
    Equaliser,
    PlayCaps,
    PlayControl,
    PlayerMode,
    PlayRepeatMode,
    PlayState,
    Preset,
)
from .nodes import (
    Endpoint,
    ListEndpoint,
    Nodes,
)

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
    "FSNotImplementedError",
    "InvalidPinError",
    "InvalidSessionError",
    "ListEndpoint",
    "Nodes",
    "OutOfRangeError",
    "PlayCaps",
    "PlayControl",
    "PlayRepeatMode",
    "PlayState",
    "PlayerMode",
    "Preset",
]
