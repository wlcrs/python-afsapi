"""Implements an asynchronous interface for a Frontier Silicon device.

For example internet radios from: Medion, Hama, Auna, ...
"""

from __future__ import annotations

import asyncio
import logging
import typing as t
from asyncio.exceptions import TimeoutError  # noqa: A004
from enum import Enum

import aiohttp
from defusedxml import ElementTree

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
from afsapi.throttler import Throttler
from afsapi.utils import maybe, unpack_xml

from .const import MAX_BASS, MAX_PLAY_RATE, MAX_TREBLE, MIN_BASS, MIN_PLAY_RATE, MIN_TREBLE

DataItem = t.Union[str, int]


DEFAULT_TIMEOUT_IN_SECONDS = 15

TIME_AFTER_READ_CALLS_IN_SECONDS = 0
TIME_AFTER_SET_CALLS_IN_SECONDS = 0.3
TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS = 1.0

FSApiValueType = Enum("FSApiValueType", "TEXT BOOL INT LONG SIGNED_LONG")

VALUE_TYPE_TO_XML_PATH = {
    FSApiValueType.TEXT: "c8_array",
    FSApiValueType.INT: "u8",
    FSApiValueType.LONG: "u32",
    FSApiValueType.SIGNED_LONG: "s32",
}

READ_ONLY = False
READ_WRITE = True

# implemented API calls
API = {
    # sys
    "power": "netRemote.sys.power",
    "mode": "netRemote.sys.mode",
    "wired_mac": "netRemote.sys.net.wired.macAddress",
    "wired_active": "netRemote.sys.net.wired.interfaceEnable",
    "wlan_mac": "netRemote.sys.net.wlan.macAddress",
    "wlan_active": "netRemote.sys.net.wlan.interfaceEnable",
    "rssi": "netRemote.sys.net.wlan.rssi",
    # sys.info
    "friendly_name": "netRemote.sys.info.friendlyName",
    "radio_id": "netRemote.sys.info.radioId",
    "version": "netRemote.sys.info.version",
    # sys.caps
    "valid_modes": "netRemote.sys.caps.validModes",
    "equalisers": "netRemote.sys.caps.eqPresets",
    "sleep": "netRemote.sys.sleep",
    # sys.audio
    "eqpreset": "netRemote.sys.audio.eqPreset",
    "eqloudness": "netRemote.sys.audio.eqLoudness",
    "bass": "netRemote.sys.audio.eqCustom.param0",
    "treble": "netRemote.sys.audio.eqCustom.param1",
    # volume
    "volume_steps": "netRemote.sys.caps.volumeSteps",
    "volume": "netRemote.sys.audio.volume",
    "mute": "netRemote.sys.audio.mute",
    # play
    "status": "netRemote.play.status",
    "name": "netRemote.play.info.name",
    "control": "netRemote.play.control",
    "shuffle": "netRemote.play.shuffle",
    "repeat": "netRemote.play.repeat",
    "position": "netRemote.play.position",
    "rate": "netRemote.play.rate",
    # info
    "text": "netRemote.play.info.text",
    "artist": "netRemote.play.info.artist",
    "album": "netRemote.play.info.album",
    "graphic_uri": "netRemote.play.info.graphicUri",
    "duration": "netRemote.play.info.duration",
    # nav
    "nav_state": "netRemote.nav.state",
    "numitems": "netRemote.nav.numItems",
    "nav_list": "netRemote.nav.list",
    "navigate": "netRemote.nav.action.navigate",
    "selectItem": "netRemote.nav.action.selectItem",
    "presets": "netRemote.nav.presets",
    "selectPreset": "netRemote.nav.action.selectPreset",
}

LOGGER = logging.getLogger(__name__)

# pylint: disable=R0904


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

        self.__modes = None
        self.__equalisers = None

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
                doc = ElementTree.fromstring(await resp.text(encoding="utf-8"))

                api = doc.find("webfsapi")
                if api is not None and api.text:
                    return api.text
                msg = f"Could not retrieve webfsapi endpoint from {fsapi_device_url}"
                raise FSApiError(
                    msg,
                )

            except (aiohttp.ServerTimeoutError, asyncio.TimeoutError) as err:
                msg = f"Did not get a response in time from {fsapi_device_url}"
                raise FSConnectionError(
                    msg,
                ) from err
            except aiohttp.ClientConnectionError as err:
                msg = f"Could not connect to {fsapi_device_url}"
                raise FSConnectionError(msg) from err

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

    # http request helpers
    async def _create_session(self) -> str | None:
        self.sid = None
        return unpack_xml(
            await self.__call("CREATE_SESSION", retry_with_session=False),
            "sessionId",
        )

    async def __call(  # noqa: C901, PLR0912
        self,
        path: str,
        extra: dict[str, DataItem] | None = None,
        *,
        force_new_session: bool = False,
        retry_with_session: bool = True,
        throttle_wait_after_call: float = TIME_AFTER_READ_CALLS_IN_SECONDS,
    ) -> ElementTree.Element:
        """Execute a frontier silicon API call."""
        params: dict[str, DataItem] = {"pin": self.pin}

        if force_new_session:
            self.sid = await self._create_session()
        if self.sid:
            params.update(sid=self.sid)

        if extra:
            params.update(**extra)

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(force_close=True),
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as client:
            try:
                async with self.__throttler.throttle(throttle_wait_after_call):
                    result = await client.get(
                        f"{self.webfsapi_endpoint}/{path}",
                        params=params,
                    )

                LOGGER.debug("Called %s with %s: %s", path, params, result.status)

                if result.status == 403:
                    msg = "Access denied - incorrect PIN"
                    raise InvalidPinError(msg)
                if result.status == 404:
                    # Bad session ID or service endpoint
                    LOGGER.warning("Service call failed with 404 to %s/%s", self.webfsapi_endpoint, path)

                    if not force_new_session and retry_with_session:
                        # retry command with a forced new session
                        return await self.__call(path, extra, force_new_session=True)
                    msg = "Wrong session-id or invalid command"
                    raise InvalidSessionError(
                        msg,
                    )
                if result.status != 200:
                    msg = f"Unexpected result {result.status}: {await result.text()}"
                    raise FSApiError(
                        msg,
                    )
                doc = ElementTree.fromstring(await result.text(encoding="utf-8"))
                status = unpack_xml(doc, "status")

                if status in {"FS_OK", "FS_LIST_END"}:
                    return doc
                if status == "FS_NODE_DOES_NOT_EXIST":
                    msg = f"FSAPI service {path} not implemented at {self.webfsapi_endpoint}."
                    raise FsNotImplementedError(
                        msg,
                    )
                if status == "FS_NODE_BLOCKED":
                    msg = "Device is not in the correct mode"
                    raise FSApiError(msg)
                if status == "FS_FAIL":
                    msg = "Command failed. Value is not in range for this command."
                    raise OutOfRangeError(
                        msg,
                    )
                if status == "FS_PACKET_BAD":
                    msg = "This command can't be SET"
                    raise FSApiError(msg)

                LOGGER.error("Unexpected FSAPI status %s", status)
                msg = f"Unexpected FSAPI status '{status}'"
                raise FSApiError(msg)
            except aiohttp.ClientConnectionError as e:
                msg = f"Could not connect to {self.webfsapi_endpoint}"
                raise FSConnectionError(msg) from e
            except TimeoutError as e:
                if not force_new_session and retry_with_session:
                    return await self.__call(path, extra, force_new_session=True)
                msg = f"{self.webfsapi_endpoint} did not respond within {self.timeout} seconds"
                raise FSConnectionError(
                    msg,
                ) from e

    # Helper methods

    # Handlers

    async def handle_get(self, item: str) -> ElementTree.Element:
        """Send a GET request for an API item.

        Args:
            item: The API item path.

        Returns:
            The XML response element.

        """
        return await self.__call(f"GET/{item}")

    async def handle_set(
        self,
        item: str,
        value: t.Any,  # noqa: ANN401
        throttle_wait_after_call: float = TIME_AFTER_SET_CALLS_IN_SECONDS,
    ) -> bool | None:
        """Send a SET request for an API item.

        Args:
            item: The API item path.
            value: The value to set.
            throttle_wait_after_call: Throttle delay after the call.

        Returns:
            True if successful, False if failed, None if no response.

        """
        status = unpack_xml(
            await self.__call(
                f"SET/{item}",
                {"value": value},
                throttle_wait_after_call=throttle_wait_after_call,
            ),
            "status",
        )
        return maybe(status, lambda x: x == "FS_OK")

    async def handle_text(self, item: str) -> str | None:
        """Extract and return text content from an API response.

        Args:
            item: The API item path.

        Returns:
            The text content, or None if not found.

        """
        return unpack_xml(await self.handle_get(item), "value/c8_array")

    async def handle_int(self, item: str) -> int | None:
        """Extract and return an unsigned 8-bit integer from an API response.

        Args:
            item: The API item path.

        Returns:
            The integer value, or None if not found.

        """
        val = unpack_xml(await self.handle_get(item), "value/u8")
        return maybe(val, int)

    async def handle_long(self, item: str) -> int | None:
        """Extract and return an unsigned 32-bit integer from an API response.

        Args:
            item: The API item path.

        Returns:
            The integer value, or None if not found.

        """
        val = unpack_xml(await self.handle_get(item), "value/u32")
        return maybe(val, int)

    async def handle_signed_long(
        self,
        item: str,
    ) -> int | None:
        """Extract and return a signed 32-bit integer from an API response.

        Args:
            item: The API item path.

        Returns:
            The integer value, or None if not found.

        """
        val = unpack_xml(await self.handle_get(item), "value/s32")
        return maybe(val, int)

    async def handle_signed_short(self, item: str) -> int | None:
        """Extract and return a signed 16-bit integer from an API response.

        Args:
            item: The API item path.

        Returns:
            The integer value, or None if not found.

        """
        val = unpack_xml(await self.handle_get(item), "value/s16")
        return maybe(val, int)

    async def handle_signed_int(self, item: str) -> int | None:
        """Extract and return a signed 8-bit integer from an API response.

        Args:
            item: The API item path.

        Returns:
            The integer value, or None if not found.

        """
        val = unpack_xml(await self.handle_get(item), "value/s8")
        return maybe(val, int)

    async def handle_list(  # noqa: C901
        self,
        list_name: str,
    ) -> t.AsyncIterable[tuple[str, dict[str, DataItem | None]]]:
        """Iterate over a list from the API, yielding items with their fields.

        Args:
            list_name: The API list path.

        Yields:
            Tuples of (item_key, field_dict) for each item in the list.

        """

        def _handle_item(
            item: ElementTree.Element,
        ) -> tuple[str, dict[str, DataItem | None]]:
            key = item.attrib["key"]

            def _handle_field(field: ElementTree.Element) -> tuple[str, DataItem | None]:
                # TODO: Handle other field types
                if "name" in field.attrib:
                    name = field.attrib["name"]
                    s = unpack_xml(field, "c8_array")
                    v = maybe(unpack_xml(field, "u8"), int)
                    return (name, s or v)
                msg = "Invalid field"
                raise ValueError(msg)

            value = dict(map(_handle_field, item.findall("field")))
            return key, value

        async def _get_next_items(
            start: int,
            count: int,
        ) -> tuple[list[ElementTree.Element], bool]:
            try:
                doc = await self.__call(
                    f"LIST_GET_NEXT/{list_name}/{start}",
                    {"maxItems": count},
                )
            except OutOfRangeError:
                return [], True
            else:
                if doc and unpack_xml(doc, "status") == "FS_OK":
                    return doc.findall("item"), doc.find("listend") is not None
                return [], True

        start = -1
        count = 50  # asking for more items gives a bigger chance on FS_NODE_BLOCKED errors on subsequent requests
        has_next = True

        while has_next:
            items, end_reached = await _get_next_items(start, count)

            for item in items:
                yield _handle_item(item)

            start += count

            if end_reached:
                has_next = False

    # sys
    async def get_friendly_name(self) -> str | None:
        """Get the friendly name of the device."""
        return await self.handle_text(API["friendly_name"])

    async def set_friendly_name(self, value: str) -> bool | None:
        """Set the friendly name of the device."""
        return await self.handle_set(API["friendly_name"], value)

    async def get_version(self) -> str | None:
        """Get the friendly name of the device."""
        return await self.handle_text(API["version"])

    async def get_radio_id(self) -> str | None:
        """Get the friendly name of the device."""
        return await self.handle_text(API["radio_id"])

    async def get_mac(self) -> str | None:
        """Get the MAC address of the device."""
        on_wlan = await self.handle_int(API["wlan_active"])
        if bool(on_wlan):
            return await self.handle_text(API["wlan_mac"])
        return await self.handle_text(API["wired_mac"])

    async def get_rssi(self) -> int | None:
        """Get the current wlan Received Signal Strength Indication in dBm."""
        # RSSI is returned as a percentage by the API, scaled linearly between
        # -80dBm (0%) and -20dBm (100%).  100% indicates a wired
        # connection.  This functions returns the dBm value of RSSI.

        rssi = await self.handle_int(API["rssi"])
        if rssi is not None:
            return round(rssi * 0.6 - 80)
        return None

    async def get_power(self) -> bool | None:
        """Check if the device is on."""
        power = await self.handle_int(API["power"])
        if power is None:
            return None
        return bool(power)

    async def set_power(
        self,
        value: bool = False,  # noqa: FBT001, FBT002
    ) -> bool | None:
        """Power on or off the device."""
        return await self.handle_set(
            API["power"],
            int(value),
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )

    async def get_volume_steps(self) -> int | None:
        """Read the maximum volume level of the device."""
        if not self.__volume_steps:
            self.__volume_steps = await self.handle_int(API["volume_steps"])

        return self.__volume_steps

    # Volume
    async def get_volume(self) -> int | None:
        """Read the volume level of the device."""
        return await self.handle_int(API["volume"])

    async def set_volume(self, value: int) -> bool | None:
        """Set the volume level of the device."""
        return await self.handle_set(API["volume"], value)

    # Mute
    async def get_mute(self) -> bool | None:
        """Check if the device is muted."""
        mute = await self.handle_int(API["mute"])
        if mute is None:
            return None
        return bool(mute)

    async def set_mute(
        self,
        value: bool = False,  # noqa: FBT001, FBT002
    ) -> bool | None:
        """Mute or unmute the device."""
        return await self.handle_set(API["mute"], int(value))

    async def get_play_status(self) -> PlayState | None:
        """Get the play status of the device."""
        status = await self.handle_int(API["status"])
        if status is not None:
            return PlayState(status)
        return None

    async def get_play_name(self) -> str | None:
        """Get the name of the played item."""
        return await self.handle_text(API["name"])

    async def get_play_text(self) -> str | None:
        """Get the text associated with the played media."""
        return await self.handle_text(API["text"])

    async def get_play_artist(self) -> str | None:
        """Get the artists of the current media(song)."""
        return await self.handle_text(API["artist"])

    async def get_play_album(self) -> str | None:
        """Get the songs's album."""
        return await self.handle_text(API["album"])

    async def get_play_graphic(self) -> str | None:
        """Get the album art associated with the song/album/artist."""
        return await self.handle_text(API["graphic_uri"])

    # Shuffle
    async def get_play_shuffle(self) -> bool | None:
        """Get the current shuffle mode (ON or OFF).

        Returns:
            True if shuffle is enabled, False if disabled, None if unavailable.

        """
        status = await self.handle_int(API["shuffle"])
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
        return await self.handle_set(API["shuffle"], int(value))

    # Repeat
    async def get_play_repeat(self) -> PlayRepeatMode | None:
        """Get the current repeat mode.

        Returns:
            The repeat mode (OFF=0, REPEAT_ALL=1, REPEAT_ONE=2), or None if unavailable.

        """
        status = await self.handle_int(API["repeat"])
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
        return await self.handle_set(API["repeat"], raw_value)

    async def get_play_duration(self) -> int | None:
        """Get the duration of the played media."""
        return await self.handle_long(API["duration"])

    async def get_play_position(self) -> int | None:
        """Get the current playback position in milliseconds.

        The user can jump to a specific moment of the track. The range of the
        value is different with every track. After the position is changed, the
        music player will continue to play the song (with the same rate).
        To find the upper bound for the current track, use `get_play_duration`.

        Returns:
            The current position in milliseconds, or None if unavailable.

        """
        return await self.handle_long(API["position"])

    async def set_play_position(self, value: int) -> bool | None:
        """Set the playback position.

        Args:
            value: The position in milliseconds.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        return await self.handle_set(API["position"], value)

    async def get_play_rate(self) -> int | None:
        """Get the current playback rate.

        Negative values (-127 to -1) rewind the track, with greater magnitude
        rewinding faster. Zero pauses playback. Positive values (1-127) play
        forward, with 127 being the fastest. Value 1 is normal speed.

        Returns:
            The playback rate in the range -127 to 127, or None if unavailable.

        """
        return await self.handle_signed_int(API["rate"])

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

        return await self.handle_set(API["rate"], value)

    # play controls

    async def play_control(self, value: PlayControl | int) -> bool | None:
        """Control the player of the device.

        1=Play; 2=Pause; 3=Next; 4=Previous (song/station)
        """
        return await self.handle_set(API["control"], int(value))

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
            self.__equalisers = [
                Equaliser(key=key, **eqinfo) async for key, eqinfo in self.handle_list(API["equalisers"])
            ]

        return self.__equalisers

    # EQ Presets
    async def get_eq_preset(self) -> Equaliser | None:
        """Get the current equaliser preset being used.

        Returns:
            The Equaliser object for the current preset, or None if unavailable.

        Raises:
            FSApiException: If the preset index is not found in the equaliser list.

        """
        v = await self.handle_int(API["eqpreset"])
        if v is None:
            return None

        for eq in await self.get_equalisers():
            if eq.key == str(v):
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
        return await self.handle_set(
            API["eqpreset"],
            int(value.key) if isinstance(value, Equaliser) else value,
        )

    # EQ Loudness (Only works with My EQ!)
    async def get_eq_loudness(self) -> bool:
        """Get the current equaliser loudness setting.

        Note: Only works when using the "My EQ" preset.

        Returns:
            True if loudness is enabled, False otherwise.

        """
        return bool(await self.handle_int(API["eqloudness"]))

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
        return await self.handle_set(API["eqloudness"], int(value))

    # Bass and Treble
    async def get_bass(self) -> int | None:
        """Get the current bass level.

        Returns:
            The bass level in range -14 to 14, or None if unavailable.

        """
        return await self.handle_signed_short(API["bass"])

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
        return await self.handle_set(API["bass"], int(value))

    async def get_treble(self) -> int | None:
        """Get the current treble level.

        Returns:
            The treble level in range -14 to 14, or None if unavailable.

        """
        return await self.handle_signed_short(API["treble"])

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

        return await self.handle_set(API["treble"], int(value))

    # Mode
    async def _get_modes(
        self,
    ) -> t.AsyncIterable[tuple[str, dict[str, DataItem | None]]]:
        async for mode in self.handle_list(API["valid_modes"]):
            yield mode

    async def get_modes(self) -> list[PlayerMode]:
        """Get the modes supported by this device."""
        # Cache as this never changes
        if self.__modes is None:
            self.__modes = [PlayerMode(key=k, **v) async for k, v in self._get_modes()]

        return self.__modes

    async def get_mode(self) -> PlayerMode | None:
        """Get the currently active mode on the device (DAB, FM, Spotify)."""
        int_mode = await self.handle_long(API["mode"])
        if int_mode is None:
            return None

        for mode in await self.get_modes():
            if mode.key == str(int_mode):
                return mode

        msg = f"Could not retrieve mode {int_mode} in modes list"
        raise FSApiError(msg)

    async def set_mode(self, value: PlayerMode | str) -> bool | None:
        """Set the currently active mode on the device (DAB, FM, Spotify)."""
        result = await self.handle_set(
            API["mode"],
            value.key if isinstance(value, PlayerMode) else value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )
        self._current_nav_path = []
        return result

    # Sleep
    async def get_sleep(self) -> int | None:
        """Check when and if the device is going to sleep."""
        return await self.handle_long(API["sleep"])

    async def set_sleep(self, value: int = 0) -> bool | None:
        """Set device sleep timer."""
        return await self.handle_set(API["sleep"], int(value))

    # Folder navigation

    async def _enable_nav_if_necessary(self) -> None:
        """Enable navigation mode if the device is not already in it."""
        nav_state = await self.handle_int(API["nav_state"])
        if nav_state != 1:
            await self.handle_set(
                API["nav_state"],
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
        return await self.handle_signed_long(API["numitems"])

    async def nav_list(
        self,
    ) -> t.AsyncIterable[tuple[str, dict[str, DataItem | None]]]:
        """List items in the current navigation path.

        Yields:
            Tuples of (item_key, field_dict) for each item in the current directory.

        """
        await self._enable_nav_if_necessary()
        return self.handle_list(API["nav_list"])

    async def nav_select_folder(self, value: int) -> bool | None:
        """Navigate into a folder.

        Args:
            value: The folder ID to navigate into.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        await self._enable_nav_if_necessary()
        result = await self.handle_set(
            API["navigate"],
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
        result = await self.handle_set(
            API["navigate"],
            "0xffffffff",
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
        return await self.handle_set(
            API["selectItem"],
            value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )

    async def nav_reset(self) -> bool | None:
        """Reset navigation to the root level.

        Returns:
            True if successful, False if failed, None if unavailable.

        """
        self._current_nav_path = []
        return await self.handle_set(API["nav_state"], 0)

    async def nav_select_folder_via_path(self, path: list[int]) -> bool | None:
        """Navigates to a target folder from the current folder in as litte steps as necessary."""
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
    ) -> t.AsyncIterable[tuple[str, dict[str, DataItem | None]]]:
        """Iterate over presets with names.

        Internal method that yields only presets that have a name field.
        """
        await self._enable_nav_if_necessary()

        async for key, preset in self.handle_list(API["presets"]):
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
            preset_fields: dict[str, DataItem | None],
        ) -> Preset:
            if not isinstance(preset_fields["name"], str):
                msg = f"Invalid type for preset name: {type(preset_fields['name'])}. Expected str."
                raise FSApiError(msg)
            type_ = str(preset_fields["type"]) if "type" in preset_fields else None
            return Preset(int(key), type_, preset_fields["name"])

        return [_to_preset(key, preset_fields) async for key, preset_fields in self._get_presets()]

    async def select_preset(self, value: Preset | int) -> bool | None:
        """Select a preset by its key."""
        await self._enable_nav_if_necessary()
        return await self.handle_set(
            API["selectPreset"],
            value.key if isinstance(value, Preset) else value,
            throttle_wait_after_call=TIME_AFTER_SLOW_SET_CALLS_IN_SECONDS,
        )
