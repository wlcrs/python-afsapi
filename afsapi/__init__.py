from .api import AFSAPI  # noqa
from afsapi.exceptions import (
    FSApiException,
    InvalidPinException,
    InvalidSessionException,
    NotImplementedException,
    OutOfRangeException,
    ConnectionError,
)
from afsapi.models import (
    Preset,
    Equaliser,
    PlayerMode,
    PlayControl,
    PlayState,
    PlayRepeatMode,
)

from importlib.metadata import version, PackageNotFoundError

try:
    VERSION = version(__name__)
except PackageNotFoundError:  # pragma: no cover
    try:
        from .version import version as VERSION  # noqa
    except ImportError:  # pragma: no cover
        VERSION = "0.0.0.dev0"
__version__ = VERSION

__all__ = [
    "AFSAPI",
    "PlayState",
    "PlayControl",
    "PlayerMode",
    "Equaliser",
    "PlayRepeatMode",
    "Preset",
    "FSApiException",
    "NotImplementedException",
    "ConnectionError",
    "OutOfRangeException",
    "InvalidPinException",
    "InvalidSessionException",
]
