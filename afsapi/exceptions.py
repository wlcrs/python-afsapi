"""Exception classes for the Frontier Silicon API library."""


class FSApiError(Exception):
    """Base exception for all Frontier Silicon API errors."""


class FsNotImplementedError(FSApiError):
    """Exception raised when an API operation is not implemented."""


class FSConnectionError(FSApiError):
    """Exception raised when connection to the device fails."""


class OutOfRangeError(FSApiError):
    """Exception raised when a value is outside the valid range."""


class InvalidPinError(FSApiError):
    """Exception raised when the provided PIN is invalid."""


class InvalidSessionError(FSApiError):
    """Exception raised when the session is invalid or has expired."""
