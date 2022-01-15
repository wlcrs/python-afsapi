"""
Implements an asynchronous interface for a Frontier Silicon device.

For example internet radios from: Medion, Hama, Auna, ...
"""

import typing as t
import logging
from afsapi.exceptions import (
    FSApiException,
    InvalidSessionException,
    OutOfRangeException,
)
from afsapi.models import Preset, Equaliser, PlayerMode, PlayControl, PlayState
from afsapi.utils import unpack_xml, maybe
from enum import Enum
import aiohttp
import xml.etree.ElementTree as ET

DataItem = t.Union[str, int]


DEFAULT_TIMEOUT_IN_SECONDS = 5

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
    # sys.info
    "friendly_name": "netRemote.sys.info.friendlyName",
    "radio_id": "netRemote.sys.info.radioId",
    "version": "netRemote.sys.info.version",
    # sys.caps
    "valid_modes": "netRemote.sys.caps.validModes",
    "equalisers": "netRemote.sys.caps.eqPresets",
    "sleep": "netRemote.sys.sleep",
    # sys.audio
    "eqpreset": "netRemote.sys.audio.eqpreset",
    "eqloudness": "netRemote.sys.audio.eqloudness",
    "bass": "netRemote.sys.audio.eqcustom.param0",
    "treble": "netRemote.sys.audio.eqcustom.param1",
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
    "numitems": "netRemote.nav.numitems",
    "nav_list": "netRemote.nav.list",
    "navigate": "netRemote.nav.action.navigate",
    "selectItem": "netRemote.nav.action.selectItem",
    "presets": "netRemote.nav.presets",
    "selectPreset": "netRemote.nav.action.selectPreset",
}

# pylint: disable=R0904


class AFSAPI:
    """Builds the interface to a Frontier Silicon device."""

    def __init__(
        self,
        webfsapi_endpoint: str,
        pin: t.Union[str, int],
        force_with_session=False,
        timeout: int = DEFAULT_TIMEOUT_IN_SECONDS,
    ):
        """Initialize the Frontier Silicon device."""
        self.webfsapi_endpoint = webfsapi_endpoint
        self.pin = str(pin)

        # Older documentation for the Frontier Silicon API seems to always use
        # a session, while this is not necessary on my device. I keep it as an
        # option for backward compatability, but disable it by default to
        # enable the usage of apps like UNDOK which need a session to function
        self.force_with_session = force_with_session
        self.timeout = timeout

        self.sid: t.Optional[str] = None
        self.__volume_steps: t.Optional[int] = None

        self.__modes = None
        self.__equalisers = None

    @staticmethod
    async def get_webfsapi_endpoint(
        fsapi_device_url: str, timeout: int = DEFAULT_TIMEOUT_IN_SECONDS
    ):

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(force_close=True),
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as client:
            try:
                resp = await client.get(fsapi_device_url)
                doc = ET.fromstring(await resp.text(encoding="utf-8"))

                api = doc.find("webfsapi")
                if api is not None and api.text:
                    return api.text
                else:
                    raise FSApiException(
                        f"Could not retrieve webfsapi endpoint from {fsapi_device_url}"
                    )

            except aiohttp.ServerTimeoutError:
                raise FSApiException(
                    f"Did not get a response in time from {fsapi_device_url}"
                )
            except aiohttp.ClientConnectionError:
                raise ConnectionError(
                    f"Could not connect to {fsapi_device_url}")

    @staticmethod
    async def create(
        fsapi_device_url: str,
        pin: t.Union[str, int],
        force_with_session=False,
        timeout: int = DEFAULT_TIMEOUT_IN_SECONDS,
    ):
        webfsapi_endpoint = await AFSAPI.get_webfsapi_endpoint(
            fsapi_device_url, timeout
        )

        return AFSAPI(webfsapi_endpoint, pin, force_with_session, timeout)

    # http request helpers
    async def _create_session(self) -> t.Optional[str]:
        return unpack_xml(
            await self.__call("CREATE_SESSION", with_session=False), "sessionId"
        )

    async def __call(
        self,
        path: str,
        extra: t.Optional[t.Dict[str, DataItem]] = None,
        with_session=None,
        force_new_session=False,
        retrying=False,
    ) -> ET.Element:
        """Execute a frontier silicon API call."""

        params: t.Dict[str, DataItem] = dict(pin=self.pin)

        if with_session or (with_session is None and self.force_with_session):
            if not self.sid or force_new_session:
                self.sid = await self._create_session()

            params.update(sid=self.sid)
        if extra:
            params.update(**extra)

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(force_close=True),
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as client:
            try:
                result = await client.get(
                    f"{self.webfsapi_endpoint}/{path}", params=params
                )

                if result.status == 403:
                    raise FSApiException("Access denied - incorrect PIN")
                elif result.status == 404:
                    # Bad session ID or service endpoint
                    logging.warn(
                        f"Service call failed with 404 to {self.webfsapi_endpoint}/{path}"
                    )

                    if with_session and not force_new_session:
                        # retry command with a forced new session
                        return await self.__call(
                            path, extra, with_session=True, force_new_session=True
                        )
                    else:
                        raise InvalidSessionException(
                            "Wrong session-id or invalid command"
                        )
                elif result.status != 200:
                    raise FSApiException(
                        f"Unexpected result {result.status}: {await result.text()}"
                    )

                doc = ET.fromstring(await result.text(encoding="utf-8"))
                status = unpack_xml(doc, "status")

                if status == "FS_OK" or status == "FS_LIST_END":
                    return doc
                elif status == "FS_NODE_DOES_NOT_EXIST":
                    raise FSApiException(
                        f"FSAPI service {path} not implemented at {self.webfsapi_endpoint}."
                    )
                elif status == "FS_NODE_BLOCKED":
                    raise FSApiException("Device is not in the correct mode")
                elif status == "FS_FAIL":
                    raise OutOfRangeException(
                        "Command failed. Value is not in range for this command."
                    )
                elif status == "FS_PACKET_BAD":
                    raise FSApiException("This command can't be SET")

                logging.error(f"Unexpected FSAPI status {status}")
                raise FSApiException(f"Unexpected FSAPI status '{status}'")
            except aiohttp.ClientConnectionError:
                raise ConnectionError(
                    f"Could not connect to {self.webfsapi_endpoint}")

    # Helper methods

    # Handlers

    async def handle_get(self, item: str, with_session=False) -> ET.Element:
        return await self.__call(f"GET/{item}", with_session)

    async def handle_set(self, item: str, value: t.Any, with_session=False) -> bool:
        status = unpack_xml(
            await self.__call(f"SET/{item}", dict(value=value), with_session), "status"
        )
        return maybe(status, lambda x: x == "FS_OK")

    async def handle_text(self, item: str, with_session=False) -> t.Optional[str]:
        return unpack_xml(await self.handle_get(item, with_session), "value/c8_array")

    async def handle_int(self, item: str, with_session=False) -> t.Optional[int]:
        val = unpack_xml(await self.handle_get(item, with_session), "value/u8")
        return maybe(val, int)

    # returns an int, assuming the value does not exceed 8 bits
    async def handle_long(self, item: str, with_session=False) -> t.Optional[int]:
        val = unpack_xml(await self.handle_get(item, with_session), "value/u32")
        return maybe(val, int)

    async def handle_signed_long(
        self, item: str, with_session=False
    ) -> t.Optional[int]:
        val = unpack_xml(await self.handle_get(item, with_session), "value/s32")
        return maybe(val, int)

    async def handle_list(
        self, list_name: str, with_session=False
    ) -> t.Iterable[t.Tuple[str, t.Dict[str, t.Optional[DataItem]]]]:
        def _handle_item(
            item: ET.Element,
        ) -> t.Tuple[str, t.Dict[str, t.Optional[DataItem]]]:
            key = item.attrib["key"]

            def _handle_field(field: ET.Element) -> t.Tuple[str, t.Optional[DataItem]]:
                # TODO: Handle other field types
                if "name" in field.attrib:
                    id = field.attrib["name"]
                    s = unpack_xml(field, "c8_array")
                    v = maybe(unpack_xml(field, "u8"), int)
                    return (id, s or v)
                return None, None

            value = dict(map(_handle_field, item.findall("field")))
            return key, value

        async def _get_next_items(start, count):
            try:
                doc = await self.__call(
                    f"LIST_GET_NEXT/{list_name}/{start}",
                    dict(
                        maxItems=count,
                    ),
                    with_session,
                )

                if doc and unpack_xml(doc, "status") == "FS_OK":
                    return doc.findall("item")
                else:
                    return None
            except OutOfRangeException:
                return None

        start = -1
        count = 25
        has_next = True

        while has_next:
            items = await _get_next_items(start, count)

            for item in items:
                yield _handle_item(item)

            start += count
            has_next = len(items) == count

    # sys
    async def get_friendly_name(self) -> t.Optional[str]:
        """Get the friendly name of the device."""
        return await self.handle_text(API["friendly_name"])

    async def set_friendly_name(self, value: str) -> t.Optional[bool]:
        """Set the friendly name of the device."""
        return await self.handle_set(API["friendly_name"], value)

    async def get_version(self) -> t.Optional[str]:
        """Get the friendly name of the device."""
        return await self.handle_text(API["version"])

    async def get_radio_id(self) -> t.Optional[str]:
        """Get the friendly name of the device."""
        return await self.handle_text(API["radio_id"])

    async def get_power(self) -> t.Optional[bool]:
        """Check if the device is on."""
        power = await self.handle_int(API["power"])
        return bool(power)

    async def set_power(self, value: bool = False) -> t.Optional[bool]:
        """Power on or off the device."""
        power = await self.handle_set(API["power"], int(value))
        return bool(power)

    async def get_volume_steps(self) -> t.Optional[int]:
        """Read the maximum volume level of the device."""
        if not self.__volume_steps:
            self.__volume_steps = await self.handle_int(API["volume_steps"])

        return self.__volume_steps

    # Volume
    async def get_volume(self) -> t.Optional[int]:
        """Read the volume level of the device."""
        return await self.handle_int(API["volume"])

    async def set_volume(self, value: int) -> t.Optional[bool]:
        """Set the volume level of the device."""
        return await self.handle_set(API["volume"], value)

    # Mute
    async def get_mute(self) -> t.Optional[bool]:
        """Check if the device is muted."""
        mute = await self.handle_int(API["mute"])
        return bool(mute)

    async def set_mute(self, value: bool = False) -> t.Optional[bool]:
        """Mute or unmute the device."""
        mute = await self.handle_set(API["mute"], int(value))
        return bool(mute)

    async def get_play_status(self) -> t.Optional[PlayState]:
        """Get the play status of the device."""
        status = await self.handle_int(API["status"])
        return PlayState(status)

    async def get_play_name(self) -> t.Optional[str]:
        """Get the name of the played item."""
        return await self.handle_text(API["name"])

    async def get_play_text(self) -> t.Optional[str]:
        """Get the text associated with the played media."""
        return await self.handle_text(API["text"])

    async def get_play_artist(self) -> t.Optional[str]:
        """Get the artists of the current media(song)."""
        return await self.handle_text(API["artist"])

    async def get_play_album(self) -> t.Optional[str]:
        """Get the songs's album."""
        return await self.handle_text(API["album"])

    async def get_play_graphic(self) -> t.Optional[str]:
        """Get the album art associated with the song/album/artist."""
        return await self.handle_text(API["graphic_uri"])

    # Shuffle
    async def get_play_shuffle(self) -> t.Optional[bool]:
        status = await self.handle_int(API["shuffle"])
        if status:
            return status == 1
        return None

    async def set_play_shuffle(self, value: bool):
        return await self.handle_set(API["shuffle"], int(value))

    # Repeat
    async def get_play_repeat(self) -> t.Optional[bool]:
        status = await self.handle_int(API["repeat"])
        if status:
            return status == 1
        return None

    async def play_repeat(self, value: bool):
        return await self.handle_set(API["repeat"], int(value))

    async def get_play_duration(self) -> t.Optional[int]:
        """Get the duration of the played media."""
        return await self.handle_long(API["duration"])

    async def get_play_position(self) -> t.Optional[int]:
        """
        The user can jump to a specific moment of the track. This means that the range of the value is
        different with every track.
        After the position is changed, the music player will continue to play the song (with the same rate).

        To find the upper bound for the current track, use `get_play_duration`
        """
        return await self.handle_int(API["position"])

    async def set_play_position(self, value: int):
        return await self.handle_set(API["position"], value)

    # Play  rate
    async def get_play_rate(self) -> t.Optional[int]:
        """
        * -127 to -1: When the user sends a negative value, the music player will rewind the track.
          The speed depends on the value, -10 will rewind faster than value -2

        * 0: When the user send rate = 0, the track will be paused
        * 1: The track will be played with normal speed
        * 2 to 127: The track will be fast forwarded, the speed is here also dependable of the value
          The speed of the fast forward is also dependable of the value, 80 is faster than 10
        """
        return await self.handle_int(API["rate"])

    async def set_play_rate(self, value: int):
        if -127 <= value <= 127:
            return await self.handle_set(API["rate"], value)
        else:
            return ValueError("Play rate must be within values -127 to 127")

    # play controls

    async def play_control(self, value: t.Union[PlayControl, int]) -> t.Optional[bool]:
        """
        Control the player of the device.

        1=Play; 2=Pause; 3=Next; 4=Previous (song/station)
        """
        return await self.handle_set(API["control"], int(value))

    async def play(self) -> t.Optional[bool]:
        """Play media."""
        return await self.play_control(PlayControl.PLAY)

    async def pause(self) -> t.Optional[bool]:
        """Pause playing."""
        return await self.play_control(PlayControl.PAUSE)

    async def forward(self) -> t.Optional[bool]:
        """Next media."""
        return await self.play_control(PlayControl.NEXT)

    async def rewind(self) -> t.Optional[bool]:
        """Previous media."""
        return await self.play_control(PlayControl.PREV)

    async def get_equalisers(self) -> t.List[Equaliser]:
        """Get the equaliser modes supported by this device."""

        # Cache as this never changes
        if self.__equalisers is None:
            self.__equalisers = [
                Equaliser(key=key, **eqinfo)
                async for key, eqinfo in self.handle_list(API["equalisers"])
            ]

        return self.__equalisers

    # EQ Presets
    async def get_eq_preset(self) -> t.Optional[Equaliser]:
        v = await self.handle_int(API["eqpreset"])
        if not v:
            return None

        for eq in await self.get_equalisers():
            if eq.key == str(v):
                return eq

        raise FSApiException(
            f"Could not retrieve equaliser {v} in equaliser list")

    async def set_eq_preset(self, value: t.Union[Equaliser, int]) -> t.Optional[bool]:
        return await self.handle_set(
            API["eqpreset"],
            int(value.key) if isinstance(value, Equaliser) else value,
        )

    # EQ Loudness (Only works with My EQ!)
    async def get_eq_loudness(self) -> bool:
        return bool(await self.handle_int(API["eqloudness"]))

    async def set_eq_loudness(self, value: bool) -> t.Optional[bool]:
        return await self.handle_set(API["eqloudness"], int(value))

    # Bass and Treble
    async def get_bass(self) -> int:
        return await self.handle_int(API["bass"])

    async def set_bass(self, value: bool) -> t.Optional[bool]:
        if -14 <= value <= 14:
            return await self.handle_set(API["bass"], int(value))
        else:
            raise ValueError("Outside of bounds: [-14, 14]")

    async def get_treble(self) -> int:
        return await self.handle_int(API["treble"])

    async def set_treble(self, value: bool) -> t.Optional[bool]:
        if -14 <= value <= 14:
            return await self.handle_set(API["treble"], int(value))
        else:
            raise ValueError("Outside of bounds: [-14, 14]")

    # Mode
    async def _get_modes(
        self,
    ) -> t.Iterable[t.Tuple[str, t.Dict[str, t.Optional[DataItem]]]]:
        async for mode in self.handle_list(API["valid_modes"]):
            yield mode

    async def get_modes(self) -> t.List[PlayerMode]:
        """Get the modes supported by this device."""

        # Cache as this never changes
        if self.__modes is None:
            self.__modes = [PlayerMode(key=k, **v) async for k, v in self._get_modes()]

        return self.__modes

    async def get_mode(self) -> t.Optional[PlayerMode]:
        """Get the currently active mode on the device (DAB, FM, Spotify)."""
        int_mode = await self.handle_long(API["mode"])
        if int_mode is None:
            return None

        for mode in await self.get_modes():
            if mode.key == str(int_mode):
                return mode

        raise FSApiException(
            f"Could not retrieve mode {int_mode} in modes list")

    async def set_mode(self, value: t.Union[PlayerMode, str]) -> t.Optional[bool]:
        """Set the currently active mode on the device (DAB, FM, Spotify)."""
        return await self.handle_set(
            API["mode"], value.key if isinstance(value, PlayerMode) else value
        )

    # Sleep
    async def get_sleep(self) -> t.Optional[int]:
        """Check when and if the device is going to sleep."""
        return await self.handle_long(API["sleep"])

    async def set_sleep(self, value: bool = False) -> t.Optional[bool]:
        """Set device sleep timer."""
        return await self.handle_set(API["sleep"], int(value))

    # Folder navigation

    async def _enable_nav_if_necessary(self):

        nav_state = await self.handle_int(API["nav_state"])
        if nav_state != 1:
            await self.handle_set(API["nav_state"], 1)

    async def nav_get_numitems(self) -> t.Optional[int]:
        await self._enable_nav_if_necessary()
        return await self.handle_signed_long(API["numitems"])

    async def nav_list(self) -> t.Iterable[t.Tuple[str, t.Dict[str, DataItem]]]:
        await self._enable_nav_if_necessary()
        return await self.handle_list(API["nav_list"])

    async def nav_select_folder(self, value: int):
        await self._enable_nav_if_necessary()
        await self.handle_set(API["navigate"], value)

    async def nav_select_parent_folder(self):
        await self._enable_nav_if_necessary()
        await self.handle_set(API["navigate"], "0xffffffff")

    async def nav_select_item(self, value: int):
        await self._enable_nav_if_necessary()
        await self.handle_set(API["selectItem"], value)

    # Presets

    async def _get_presets(
        self,
    ) -> t.Iterable[t.Tuple[str, t.Dict[str, t.Optional[DataItem]]]]:
        await self._enable_nav_if_necessary()

        async for key, preset in self.handle_list(API["presets"]):
            if preset.get("name"):
                # Strip whitespaces from names
                preset["name"] = preset["name"].strip()
                yield key, preset
            else:
                # Skip empty preset
                pass

    async def get_presets(self) -> t.List[Preset]:

        # We don't cache this call as it changes when the mode changes

        return [
            Preset(key=int(key), **preset_fields)
            async for key, preset_fields in self._get_presets()
        ]

    async def select_preset(self, value: t.Union[Preset, int]):
        await self._enable_nav_if_necessary()
        return await self.handle_set(
            API["selectPreset"],
            value.key if isinstance(value, Preset) else value,
        )
