"""Implements an asynchronous interface for a Frontier Silicon device.

For example internet radios from: Medion, Hama, Auna, ...
"""

from __future__ import annotations

import asyncio
import logging
import typing as t

import aiohttp
from defusedxml import ElementTree

from afsapi.exceptions import (
    FSApiError,
    FSConnectionError,
    InvalidPinError,
    InvalidSessionError,
    OutOfRangeError,
)
from afsapi.models import (
    Equaliser,
    PlayCaps,
    PlayControl,
    PlayerMode,
    PlayRepeatMode,
    PlayState,
    Preset,
)
from afsapi.nodes import (
    Endpoint,
    ListEndpoint,
    NavListItem,
    Nodes,
    PresetsListItem,
    ValidModesListItem,
)
from afsapi.response import (
    FSAPIStatus,
    extract_item_fields,
    extract_item_key,
    extract_list_items,
    extract_text,
    parse_status,
)
from afsapi.throttler import Throttler
from afsapi.utils import maybe

from .const import MAX_BASS, MAX_PLAY_RATE, MAX_TREBLE, MIN_BASS, MIN_PLAY_RATE, MIN_TREBLE

if t.TYPE_CHECKING:
    from xml.etree import ElementTree as ET

V = t.TypeVar("V", bound=str | int)
ListValue = t.TypeVar("ListValue")


DEFAULT_TIMEOUT_IN_SECONDS = 15

TIME_AFTER_READ_CALLS_IN_SECONDS = 0
TIME_AFTER_SET_CALLS_IN_SECONDS = 0.3
TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS = 1.0
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404

# Backward-compatible path lookup dict.
# New code should use typed ``Nodes.*`` attributes + ``AFSAPI.get()`` instead.
API: dict[str, str] = {
    name: endpoint.path for name, endpoint in vars(Nodes).items() if isinstance(endpoint, (Endpoint, ListEndpoint))
}

LOGGER = logging.getLogger(__name__)


# pylint: disable-next=too-many-public-methods,too-many-instance-attributes
class AFSAPI:
    """Builds the interface to a Frontier Silicon device."""

    def __init__(
        self,
        webfsapi_endpoint: str,
        pin: str | int,
        timeout: int = DEFAULT_TIMEOUT_IN_SECONDS,
    ) -> None:
        """Initialize the Frontier Silicon device client.

        Args:
            webfsapi_endpoint: The webfsapi endpoint URL of the device.
            pin: The device PIN for authentication.
            timeout: Timeout in seconds for HTTP requests.

        """
        self.webfsapi_endpoint = webfsapi_endpoint
        self.pin = str(pin)
        self.timeout = timeout

        self.sid: str | None = None
        self.__volume_steps: int | None = None

        self.__modes: list[PlayerMode] | None = None
        self.__equalisers: list[Equaliser] | None = None
        self._http_session: aiohttp.ClientSession | None = None

        self._current_nav_path: list[int] = []

        self.__throttler = Throttler()

    @staticmethod
    async def get_webfsapi_endpoint(
        fsapi_device_url: str,
        timeout: int = DEFAULT_TIMEOUT_IN_SECONDS,
    ) -> str:
        """Retrieve the webfsapi endpoint URL from a Frontier Silicon device.

        Args:
            fsapi_device_url: The base URL of the device.
            timeout: Timeout in seconds for the HTTP request.

        Returns:
            The webfsapi endpoint URL.

        Raises:
            FSApiException: If the endpoint cannot be retrieved.
            ConnectionError: If the device cannot be contacted.

        """
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(force_close=True),
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as client:
            try:
                resp = await client.get(fsapi_device_url)
                resp.raise_for_status()
                doc = ElementTree.fromstring(await resp.text(encoding="utf-8", errors="replace"))

                api = doc.find("webfsapi")
                if api is not None and api.text:
                    return api.text
                msg = f"Could not retrieve webfsapi endpoint from {fsapi_device_url}"
                raise FSApiError(
                    msg,
                )

            except (aiohttp.ServerTimeoutError, TimeoutError) as err:
                msg = f"Did not get a response in time from {fsapi_device_url}"
                raise FSConnectionError(
                    msg,
                ) from err
            except aiohttp.ClientConnectionError as err:
                msg = f"Could not connect to {fsapi_device_url}"
                raise FSConnectionError(msg) from err
            except aiohttp.ClientResponseError as err:
                msg = f"Unexpected HTTP response {err.status} while retrieving endpoint from {fsapi_device_url}"
                raise FSApiError(msg) from err

    @staticmethod
    async def create(
        fsapi_device_url: str,
        pin: str | int,
        timeout: int = DEFAULT_TIMEOUT_IN_SECONDS,
    ) -> AFSAPI:
        """Create an AFSAPI instance by discovering the webfsapi endpoint.

        Args:
            fsapi_device_url: The base URL of the device.
            pin: The PIN for device access.
            timeout: Timeout in seconds for HTTP requests.

        Returns:
            An initialized AFSAPI instance.

        """
        webfsapi_endpoint = await AFSAPI.get_webfsapi_endpoint(
            fsapi_device_url,
            timeout,
        )

        return AFSAPI(webfsapi_endpoint, pin, timeout)

    async def __aenter__(self) -> AFSAPI:  # noqa: PYI034
        """Enter async context and initialize the shared HTTP session."""
        await self._get_http_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        """Exit async context and close the shared HTTP session."""
        del exc_type, exc, tb
        await self.close()

    async def close(self) -> None:
        """Close the shared HTTP session used by this client instance."""
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
        self._http_session = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Return a reusable HTTP session, creating it on first use."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(force_close=True),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._http_session

    # Generic typed endpoint access

    @t.overload
    async def get(self, endpoint: Endpoint[str]) -> str | None: ...

    @t.overload
    async def get(self, endpoint: Endpoint[int]) -> int | None: ...

    @t.overload
    async def get(self, endpoint: ListEndpoint[ListValue]) -> list[tuple[str, ListValue]]: ...

    async def get(
        self,
        endpoint: Endpoint[str] | Endpoint[int] | ListEndpoint[ListValue],
    ) -> str | int | list[tuple[str, ListValue]] | None:
        """Fetch the current value of a typed FSAPI endpoint.

        For scalar endpoints the return type is inferred from the endpoint
        descriptor (``Endpoint[int]`` → ``int | None``, ``Endpoint[str]``
        → ``str | None``).  For list endpoints the method collects all items
        and returns a ``list[tuple[str, T]]``.

        Args:
            endpoint: A typed endpoint descriptor from :class:`Nodes`.

        Returns:
            The parsed value for scalar endpoints, a collected list of
            ``(key, item_dict)`` tuples for list endpoints, or ``None``
            when the device returns no value.

        Example::

            name = await api.get(Nodes.friendly_name)   # str | None
            vol  = await api.get(Nodes.volume)           # int | None
            eqs  = await api.get(Nodes.equalisers)       # list[…]

        """
        if isinstance(endpoint, ListEndpoint):
            items = [(key, item) async for key, item in self.handle_list(endpoint.path)]
            return t.cast("list[tuple[str, ListValue]]", items)
        doc = await self.handle_get(endpoint.path)
        val = extract_text(doc, "value", endpoint.xml_tag)
        if val is None:
            return None
        if endpoint.is_string_type:
            return val
        return maybe(val, int)

    async def _create_session(self) -> str | None:
        self.sid = None
        return extract_text(
            await self.__call("CREATE_SESSION", retry_with_session=False),
            "sessionId",
        )

    # pylint: disable-next=too-many-arguments
    async def __call(  # noqa: C901
        self,
        path: str,
        extra: dict[str, str | int] | None = None,
        *,
        force_new_session: bool = False,
        retry_with_session: bool = True,
        throttle_wait_after_call: float = TIME_AFTER_READ_CALLS_IN_SECONDS,
    ) -> ET.Element:
        """Execute a frontier silicon API call."""
        params: dict[str, str | int] = {"pin": self.pin}

        if force_new_session:
            self.sid = await self._create_session()
        if self.sid:
            params.update(sid=self.sid)

        if extra:
            params.update(**extra)

        client = await self._get_http_session()

        try:
            async with self.__throttler.throttle(throttle_wait_after_call):
                result = await client.get(
                    f"{self.webfsapi_endpoint}/{path}",
                    params=params,
                )

            LOGGER.debug("Called %s with %s: %s", path, params, result.status)
            result.raise_for_status()

        except aiohttp.ClientResponseError as err:
            if err.status == HTTP_STATUS_FORBIDDEN:
                msg = "Access denied - incorrect PIN"
                raise InvalidPinError(msg) from err
            if err.status == HTTP_STATUS_NOT_FOUND:
                LOGGER.warning("Service call failed with 404 to %s/%s", self.webfsapi_endpoint, path)

                if not force_new_session and retry_with_session:
                    return await self.__call(path, extra, force_new_session=True)
                msg = "Wrong session-id or invalid command"
                raise InvalidSessionError(msg) from err
            msg = f"Unexpected HTTP response {err.status}"
            raise FSApiError(msg) from err
        except (aiohttp.ServerTimeoutError, asyncio.TimeoutError, TimeoutError) as err:  # pylint: disable=bad-except-order
            if not force_new_session and retry_with_session:
                return await self.__call(path, extra, force_new_session=True)
            msg = f"{self.webfsapi_endpoint} did not respond within {self.timeout} seconds"
            raise FSConnectionError(msg) from err
        except aiohttp.ClientConnectionError as err:
            msg = f"Could not connect to {self.webfsapi_endpoint}"
            raise FSConnectionError(msg) from err

        doc = ElementTree.fromstring(await result.text(encoding="utf-8", errors="replace"))
        parse_status(doc).raise_for_status()
        return doc

    # Helper methods

    # Handlers

    async def handle_get(self, item: str) -> ET.Element:
        """Send a GET request for an API item.

        Args:
            item: The API item path.

        Returns:
            The XML response element.

        """
        return await self.__call(f"GET/{item}")

    async def set(
        self,
        endpoint: Endpoint[V],
        value: V,
        throttle_wait_after_call: float = TIME_AFTER_SET_CALLS_IN_SECONDS,
    ) -> bool:
        """Set the value of a typed FSAPI endpoint.

        Args:
            endpoint: A scalar endpoint descriptor from :class:`Nodes`.
            value: The value to set.
            throttle_wait_after_call: Throttle delay after the call.

        Returns:
            True if successful, False if failed, None if no response.

        """
        response = await self.__call(
            f"SET/{endpoint.path}",
            {"value": value},
            throttle_wait_after_call=throttle_wait_after_call,
        )
        status = parse_status(response)
        return status == FSAPIStatus.FS_OK

    @staticmethod
    def _parse_field_value(tag: str, value: str) -> str | int | None:
        """Parse field value based on XML tag type.

        Supports all FSAPI field types from fsapi-tools:
        - c8_array: String (char array)
        - array: Generic array (string)
        - u8, u16, u32: Unsigned integers
        - s8, s16, s32: Signed integers
        - e8: Enum value (as integer)

        Args:
            tag: The XML tag name (e.g., 'c8_array', 'u8', 's16').
            value: The text value to parse.

        Returns:
            Parsed value as appropriate type, or None if conversion fails.

        """
        # Normalize tag by removing _array suffix for comparison
        normalized_tag = tag.replace("_array", "").lower()

        # String types - return as-is
        if normalized_tag in {"c8", "array"}:
            return value

        # Integer types - convert to int or return None
        if normalized_tag in {"u8", "u16", "u32", "s8", "s16", "s32", "e8"}:
            return maybe(value, int)

        # Unknown type - return as string
        return value

    @staticmethod
    def _handle_item(
        item: ET.Element,
    ) -> tuple[str, dict[str, str | int | None]]:
        """Extract key and fields from a list item element.

        Args:
            item: The item element from the list response.

        Returns:
            Tuple of (key_str, field_dict) with parsed field values.

        """
        key = extract_item_key(item, default=-1)
        fields = extract_item_fields(item)

        value = {}
        for name, (tag, text) in fields.items():
            value[name] = AFSAPI._parse_field_value(tag, text)

        return str(key), value

    async def _get_next_items(
        self,
        list_name: str,
        start: int,
        count: int,
    ) -> tuple[list[ET.Element], bool]:
        """Fetch next batch of items from the list.

        Args:
            list_name: The API list path.
            start: Starting position in the list.
            count: Number of items to retrieve.

        Returns:
            Tuple of (item_elements, has_reached_end).

        """
        try:
            doc = await self.__call(
                f"LIST_GET_NEXT/{list_name}/{start}",
                {"maxItems": count},
            )
        except OutOfRangeError:
            return [], True

        status = parse_status(doc)
        if status == FSAPIStatus.FS_OK:
            items = extract_list_items(doc)
            has_ended = doc.find("listend") is not None
            return items, has_ended

        return [], True

    async def handle_list(
        self,
        list_name: str,
    ) -> t.AsyncIterable[tuple[str, dict[str, str | int | None]]]:
        """Iterate over a list from the API, yielding items with their fields.

        Args:
            list_name: The API list path.

        Yields:
            Tuples of (item_key, field_dict) where field values are strings or ints.

        Note:
            For properly typed responses, prefer using specific methods like
            get_equalisers(), get_modes(), get_presets(), or nav_list()
            which return structured data types.

        """
        start = -1
        count = 50  # asking for more items gives a bigger chance on FS_NODE_BLOCKED errors on subsequent requests
        has_next = True

        while has_next:
            items, end_reached = await self._get_next_items(list_name, start, count)

            for item in items:
                yield self._handle_item(item)

            start += count

            if end_reached:
                has_next = False

    # sys
    async def get_friendly_name(self) -> str | None:
        """Get the friendly name of the device."""
        return await self.get(Nodes.friendly_name)

    async def set_friendly_name(self, value: str) -> bool | None:
        """Set the friendly name of the device."""
        return await self.set(Nodes.friendly_name, value)

    async def get_version(self) -> str | None:
        """Get the friendly name of the device."""
        return await self.get(Nodes.version)

    async def get_radio_id(self) -> str | None:
        """Get the friendly name of the device."""
        return await self.get(Nodes.radio_id)

    async def get_mac(self) -> str | None:
        """Get the MAC address of the device."""
        on_wlan = await self.get(Nodes.wlan_active)
        if bool(on_wlan):
            return await self.get(Nodes.wlan_mac)
        return await self.get(Nodes.wired_mac)

    async def get_rssi(self) -> int | None:
        """Get the current wlan Received Signal Strength Indication in dBm."""
        # RSSI is returned as a percentage by the API, scaled linearly between
        # -80dBm (0%) and -20dBm (100%).  100% indicates a wired
        # connection.  This functions returns the dBm value of RSSI.

        rssi = await self.get(Nodes.rssi)
        if rssi is not None:
            return round(rssi * 0.6 - 80)
        return None

    async def get_power(self) -> bool | None:
        """Check if the device is on."""
        power = await self.get(Nodes.power)
        if power is None:
            return None
        return bool(power)

    async def set_power(
        self,
        value: bool = False,  # noqa: FBT001, FBT002
    ) -> bool | None:
        """Power on or off the device."""
        return await self.set(
            Nodes.power,
            int(value),
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )

    async def get_volume_steps(self) -> int | None:
        """Read the maximum volume level of the device."""
        if not self.__volume_steps:
            self.__volume_steps = await self.get(Nodes.volume_steps)

        return self.__volume_steps

    # Volume
    async def get_volume(self) -> int | None:
        """Read the volume level of the device."""
        return await self.get(Nodes.volume)

    async def set_volume(self, value: int) -> bool | None:
        """Set the volume level of the device."""
        return await self.set(Nodes.volume, value)

    # Mute
    async def get_mute(self) -> bool | None:
        """Check if the device is muted."""
        mute = await self.get(Nodes.mute)
        if mute is None:
            return None
        return bool(mute)

    async def set_mute(
        self,
        value: bool = False,  # noqa: FBT001, FBT002
    ) -> bool | None:
        """Mute or unmute the device."""
        return await self.set(Nodes.mute, int(value))

    async def get_play_status(self) -> PlayState | None:
        """Get the play status of the device."""
        status = await self.get(Nodes.status)
        if status is not None:
            return PlayState(status)
        return None

    async def get_play_caps(self) -> PlayCaps | None:
        """Get the supported play control capabilities of the device."""
        caps = await self.get(Nodes.caps)
        if caps is not None:
            return PlayCaps(caps)
        return None

    async def get_play_name(self) -> str | None:
        """Get the name of the played item."""
        return await self.get(Nodes.name)

    async def get_play_text(self) -> str | None:
        """Get the text associated with the played media."""
        return await self.get(Nodes.text)

    async def get_play_artist(self) -> str | None:
        """Get the artists of the current media(song)."""
        return await self.get(Nodes.artist)

    async def get_play_album(self) -> str | None:
        """Get the songs's album."""
        return await self.get(Nodes.album)

    async def get_play_graphic(self) -> str | None:
        """Get the album art associated with the song/album/artist."""
        return await self.get(Nodes.graphic_uri)

    # Shuffle
    async def get_play_shuffle(self) -> bool | None:
        """Get the current shuffle mode (ON or OFF).

        Returns:
            True if shuffle is enabled, False if disabled, None if unavailable.

        """
        status = await self.get(Nodes.shuffle)
        if status is not None:
            return status == 1
        return None

    async def set_play_shuffle(
        self,
        value: bool,  # noqa: FBT001
    ) -> bool | None:
        """Set the shuffle mode.

        Args:
            value: True to enable shuffle, False to disable.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        return await self.set(Nodes.shuffle, int(value))

    # Repeat
    async def get_play_repeat(self) -> PlayRepeatMode | None:
        """Get the current repeat mode.

        Returns:
            The repeat mode (OFF=0, REPEAT_ALL=1, REPEAT_ONE=2), or None if unavailable.

        """
        status = await self.get(Nodes.repeat)
        if status is not None:
            return PlayRepeatMode(status)
        return None

    async def play_repeat(
        self,
        value: PlayRepeatMode | bool | int,  # noqa: FBT001
    ) -> bool | None:
        """Set the repeat mode.

        Args:
            value: Repeat mode as PlayRepeatMode enum, bool, or int (0-2).

        Returns:
            True if successful, False if failed, None if unavailable.

        Raises:
            ValueError: If value is not a valid repeat mode.

        """
        raw_value = int(value) if isinstance(value, (PlayRepeatMode, bool)) else value

        if raw_value not in (0, 1, 2):
            msg = "Repeat mode must be one of 0 (OFF), 1 (REPEAT_ALL), 2 (REPEAT_ONE)"
            raise ValueError(
                msg,
            )
        return await self.set(Nodes.repeat, raw_value)

    async def get_play_duration(self) -> int | None:
        """Get the duration of the played media."""
        return await self.get(Nodes.duration)

    async def get_play_position(self) -> int | None:
        """Get the current playback position in milliseconds.

        The user can jump to a specific moment of the track. The range of the
        value is different with every track. After the position is changed, the
        music player will continue to play the song (with the same rate).
        To find the upper bound for the current track, use `get_play_duration`.

        Returns:
            The current position in milliseconds, or None if unavailable.

        """
        return await self.get(Nodes.position)

    async def set_play_position(self, value: int) -> bool | None:
        """Set the playback position.

        Args:
            value: The position in milliseconds.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        return await self.set(Nodes.position, value)

    async def get_play_rate(self) -> int | None:
        """Get the current playback rate.

        Negative values (-127 to -1) rewind the track, with greater magnitude
        rewinding faster. Zero pauses playback. Positive values (1-127) play
        forward, with 127 being the fastest. Value 1 is normal speed.

        Returns:
            The playback rate in the range -127 to 127, or None if unavailable.

        """
        return await self.get(Nodes.rate)

    async def set_play_rate(self, value: int) -> bool | None:
        """Set the playback rate.

        Args:
            value: Playback rate in range -127 to 127.

        Returns:
            True if successful, False if failed, None if unavailable.

        Raises:
            ValueError: If value is not in the range -127 to 127.

        """
        if not (MIN_PLAY_RATE <= value <= MAX_PLAY_RATE):
            msg = f"Play rate must be within values {MIN_PLAY_RATE} to {MAX_PLAY_RATE}"
            raise ValueError(msg)

        return await self.set(Nodes.rate, value)

    # play controls

    async def play_control(self, value: PlayControl | int) -> bool | None:
        """Control the player of the device.

        1=Play; 2=Pause; 3=Next; 4=Previous (song/station)
        """
        return await self.set(Nodes.control, int(value))

    async def stop(self) -> bool | None:
        """Stop playing."""
        return await self.play_control(PlayControl.STOP)

    async def play(self) -> bool | None:
        """Play media."""
        return await self.play_control(PlayControl.PLAY)

    async def pause(self) -> bool | None:
        """Pause playing."""
        return await self.play_control(PlayControl.PAUSE)

    async def forward(self) -> bool | None:
        """Next media."""
        return await self.play_control(PlayControl.NEXT)

    async def rewind(self) -> bool | None:
        """Previous media."""
        return await self.play_control(PlayControl.PREV)

    async def get_equalisers(self) -> list[Equaliser]:
        """Get the equaliser modes supported by this device."""
        # Cache as this never changes
        if self.__equalisers is None:
            equalisers = await self.get(Nodes.equalisers)
            self.__equalisers = [Equaliser(key=int(key), label=eqinfo["label"]) for key, eqinfo in equalisers]

        return self.__equalisers

    # EQ Presets
    async def get_eq_preset(self) -> Equaliser | None:
        """Get the current equaliser preset being used.

        Returns:
            The Equaliser object for the current preset, or None if unavailable.

        Raises:
            FSApiException: If the preset index is not found in the equaliser list.

        """
        v = await self.get(Nodes.eqpreset)
        if v is None:
            return None

        for eq in await self.get_equalisers():
            if eq.key == v:
                return eq

        msg = f"Could not retrieve equaliser {v} in equaliser list"
        raise FSApiError(msg)

    async def set_eq_preset(self, value: Equaliser | int) -> bool | None:
        """Set the active equaliser preset.

        Args:
            value: Equaliser object or preset key as integer.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        return await self.set(
            Nodes.eqpreset,
            int(value.key) if isinstance(value, Equaliser) else value,
        )

    # EQ Loudness (Only works with My EQ!)
    async def get_eq_loudness(self) -> bool:
        """Get the current equaliser loudness setting.

        Note: Only works when using the "My EQ" preset.

        Returns:
            True if loudness is enabled, False otherwise.

        """
        return bool(await self.get(Nodes.eqloudness))

    async def set_eq_loudness(
        self,
        value: bool,  # noqa: FBT001
    ) -> bool | None:
        """Set the equaliser loudness setting.

        Note: Only works when using the "My EQ" preset.

        Args:
            value: True to enable loudness, False to disable.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        return await self.set(Nodes.eqloudness, int(value))

    # Bass and Treble
    async def get_bass(self) -> int | None:
        """Get the current bass level.

        Returns:
            The bass level in range -14 to 14, or None if unavailable.

        """
        return await self.get(Nodes.bass)

    async def set_bass(self, value: int) -> bool | None:
        """Set the bass level.

        Args:
            value: Bass level in range -14 to 14.

        Returns:
            True if successful, False if failed, None if unavailable.

        Raises:
            ValueError: If value is outside the range -14 to 14.

        """
        if not (MIN_BASS <= value <= MAX_BASS):
            msg = f"Outside of bounds: [{MIN_BASS}, {MAX_BASS}]"
            raise ValueError(msg)
        return await self.set(Nodes.bass, int(value))

    async def get_treble(self) -> int | None:
        """Get the current treble level.

        Returns:
            The treble level in range -14 to 14, or None if unavailable.

        """
        return await self.get(Nodes.treble)

    async def set_treble(self, value: int) -> bool | None:
        """Set the treble level.

        Args:
            value: Treble level in range -14 to 14.

        Returns:
            True if successful, False if failed, None if unavailable.

        Raises:
            ValueError: If value is outside the range -14 to 14.

        """
        if not (MIN_TREBLE <= value <= MAX_TREBLE):
            msg = f"Outside of bounds: [{MIN_TREBLE}, {MAX_TREBLE}]"
            raise ValueError(msg)

        return await self.set(Nodes.treble, int(value))

    # Mode
    async def _get_modes(self) -> t.AsyncIterable[tuple[str, ValidModesListItem]]:
        for mode in await self.get(Nodes.valid_modes):
            yield mode

    async def get_modes(self) -> list[PlayerMode]:
        """Get the modes supported by this device."""
        # Cache as this never changes
        if self.__modes is None:
            self.__modes = [
                PlayerMode(
                    id=v["id"],
                    key=int(k),
                    label=v.get("label"),
                    selectable=v.get("selectable"),
                    streamable=v.get("streamable"),
                    modetype=v.get("modeType"),
                )
                async for k, v in self._get_modes()
            ]

        return self.__modes

    async def get_mode(self) -> PlayerMode | None:
        """Get the currently active mode on the device (DAB, FM, Spotify)."""
        int_mode = await self.get(Nodes.mode)
        if int_mode is None:
            return None

        for mode in await self.get_modes():
            if mode.key == int_mode:
                return mode

        msg = f"Could not retrieve mode {int_mode} in modes list"
        raise FSApiError(msg)

    async def set_mode(self, value: PlayerMode | str) -> bool | None:
        """Set the currently active mode on the device (DAB, FM, Spotify)."""
        mode_value = int(value.key) if isinstance(value, PlayerMode) else int(value)
        result = await self.set(
            Nodes.mode,
            mode_value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )
        self._current_nav_path = []
        return result

    # Sleep
    async def get_sleep(self) -> int | None:
        """Check when and if the device is going to sleep."""
        return await self.get(Nodes.sleep)

    async def set_sleep(self, value: int = 0) -> bool | None:
        """Set device sleep timer."""
        return await self.set(Nodes.sleep, int(value))

    # Folder navigation

    async def _enable_nav_if_necessary(self) -> None:
        """Enable navigation mode if the device is not already in it."""
        nav_state = await self.get(Nodes.nav_state)
        if nav_state != 1:
            await self.set(
                Nodes.nav_state,
                1,
                throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
                # changing to navigation can be very slow!
            )

            # the nav path is empty, as we needed to set the radio into nav-mode
            self._current_nav_path = []

    async def nav_get_numitems(self) -> int | None:
        """Get the number of items in the current navigation path.

        Returns:
            The number of items, or None if unavailable.

        """
        await self._enable_nav_if_necessary()
        return await self.get(Nodes.numitems)

    async def nav_list(
        self,
    ) -> t.AsyncIterable[tuple[str, NavListItem]]:
        """List items in the current navigation path.

        Yields:
            Tuples of (item_key, field_dict) for each item in the current directory.

        """
        await self._enable_nav_if_necessary()
        for item in await self.get(Nodes.nav_list):
            yield item

    async def nav_select_folder(self, value: int) -> bool | None:
        """Navigate into a folder.

        Args:
            value: The folder ID to navigate into.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        await self._enable_nav_if_necessary()
        result = await self.set(
            Nodes.navigate,
            value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )
        self._current_nav_path.append(value)

        return result

    async def nav_select_parent_folder(self) -> bool | None:
        """Navigate to the parent folder.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        await self._enable_nav_if_necessary()
        result = await self.set(
            Nodes.navigate,
            0xFFFFFFFF,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )
        if self._current_nav_path:
            self._current_nav_path.pop()

        return result

    async def nav_select_item(self, value: int) -> bool | None:
        """Select an item in the current navigation path.

        Args:
            value: The item ID to select.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        await self._enable_nav_if_necessary()
        return await self.set(
            Nodes.select_item,
            value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )

    async def nav_reset(self) -> bool | None:
        """Reset navigation to the root level.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        self._current_nav_path = []
        return await self.set(Nodes.nav_state, 0)

    async def nav_select_folder_via_path(self, path: list[int]) -> bool | None:
        """Navigates to a target folder from the current folder in as little steps as necessary."""
        result = None

        LOGGER.debug("Navigating to %s, currently in %s", path, self._current_nav_path)

        while len(self._current_nav_path) > len(path):
            LOGGER.debug("Going up to parent folder in %s", self._current_nav_path)
            result = await self.nav_select_parent_folder()

        key_idx = 0
        while key_idx < len(path):
            key = int(path[key_idx])
            if key_idx >= len(self._current_nav_path):
                LOGGER.debug("Selecting %s in %s", key, self._current_nav_path)
                result = await self.nav_select_folder(key)
                key_idx += 1
            elif key != self._current_nav_path[key_idx]:
                LOGGER.debug("Going up to parent folder in %s", self._current_nav_path)
                result = await self.nav_select_parent_folder()
            else:
                key_idx += 1

        return result

    async def nav_select_item_via_path(self, path: list[int]) -> bool | None:
        """Select an item by navigating via a path of folder IDs.

        Args:
            path: List of folder IDs to navigate through, with the item ID as the last element.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        await self.nav_select_folder_via_path(path[:-1])
        return await self.nav_select_item(path[-1])

    # Presets

    async def _get_presets(
        self,
    ) -> t.AsyncIterable[tuple[str, PresetsListItem]]:
        """Iterate over presets with names.

        Internal method that yields only presets that have a name field.
        """
        await self._enable_nav_if_necessary()

        for key, preset in await self.get(Nodes.presets):
            if preset.get("name"):
                # Strip whitespaces from names
                if not isinstance(preset["name"], str):
                    msg = f"Invalid type for preset name: {type(preset['name'])}. Expected str."
                    raise FSApiError(msg)
                preset["name"] = preset["name"].strip()
                yield key, preset
            else:
                # Skip empty preset
                pass

    async def get_presets(self) -> list[Preset]:
        """Get the list of presets with their names."""
        # We don't cache this call as it changes when the mode changes

        def _to_preset(
            key: str,
            preset_fields: PresetsListItem,
        ) -> Preset:
            return Preset(int(key), preset_fields.get("type"), preset_fields["name"])

        return [_to_preset(key, preset_fields) async for key, preset_fields in self._get_presets()]

    async def select_preset(self, value: Preset | int) -> bool | None:
        """Select a preset by its key."""
        await self._enable_nav_if_necessary()
        return await self.set(
            Nodes.select_preset,
            value.key if isinstance(value, Preset) else value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )
