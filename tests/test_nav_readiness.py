"""Navigation list readiness regressions without live device access."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from afsapi.api import AFSAPI
from afsapi.exceptions import (
    FSApiError,
    FSConnectionError,
    FSNodeBlockedError,
    InvalidPinError,
    InvalidSessionError,
    OutOfRangeError,
)
from afsapi.nodes import Nodes
from defusedxml import ElementTree


@pytest.mark.asyncio
async def test_blocked_navigation_list_becomes_ready() -> None:
    """Retry a blocked read without repeating navigation commands."""
    api = AFSAPI("http://mock", "0000")
    ready = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="name"><c8_array>Stations</c8_array></field>'
        '<field name="type"><u8>0</u8></field></item><listend/></fsapiResponse>',
    )
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[FSNodeBlockedError("loading"), ready]) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        items = await api.get(Nodes.nav_list)
    assert items == [("0", {"name": "Stations", "type": 0})]
    assert call.call_count == 2  # noqa: PLR2004
    sleep.assert_awaited_once_with(1.0)
    assert all(args.args[0].startswith("LIST_GET_NEXT/") for args in call.call_args_list)


@pytest.mark.asyncio
async def test_loading_placeholder_becomes_ready() -> None:
    """Do not return the unnamed type-255 loading entry as real content."""
    api = AFSAPI("http://mock", "0000")
    loading = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="name"><c8_array/></field>'
        '<field name="type"><u8>255</u8></field>'
        '<field name="subtype"><u8>0</u8></field>'
        '<field name="contextmenu"><u8>0</u8></field></item><listend/></fsapiResponse>',
    )
    empty = ElementTree.fromstring("<fsapiResponse><status>FS_OK</status><listend/></fsapiResponse>")
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[loading, empty]) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        items = await api.get(Nodes.nav_list)
    assert items == []
    assert call.call_count == 2  # noqa: PLR2004
    sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("loading", [False, True])
async def test_readiness_retries_are_bounded(*, loading: bool) -> None:
    """Exhaustion raises rather than returning a placeholder or an empty folder."""
    api = AFSAPI("http://mock", "0000")
    error = FSNodeBlockedError("still blocked")
    response = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="type"><u8>255</u8></field></item><listend/></fsapiResponse>',
    )
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[response if loading else error] * 8) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(FSNodeBlockedError) as raised,
    ):
        await api.get(Nodes.nav_list)
    assert call.call_count == 8  # noqa: PLR2004
    assert sleep.await_count == 7  # noqa: PLR2004
    assert all(args.args == (1.0,) for args in sleep.await_args_list)
    if loading:
        assert "type 255" in str(raised.value)
    else:
        assert raised.value is error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [FSApiError, FSConnectionError, InvalidPinError, InvalidSessionError, asyncio.CancelledError],
)
async def test_other_errors_are_not_retried(error_type: type[BaseException]) -> None:
    """Preserve real errors and cancellation, even after a transient failure."""
    api = AFSAPI("http://mock", "0000")
    error = error_type("stop")
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[FSNodeBlockedError("loading"), error]) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(error_type) as raised,
    ):
        await api.get(Nodes.nav_list)
    assert raised.value is error
    assert call.call_count == 2  # noqa: PLR2004
    sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_cancellation_during_retry_delay() -> None:
    """A caller can cancel the readiness wait immediately."""
    api = AFSAPI("http://mock", "0000")
    with (
        patch.object(api, "_AFSAPI__call", side_effect=FSNodeBlockedError("loading")) as call,
        patch("afsapi.api.asyncio.sleep", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await api.get(Nodes.nav_list)
    call.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("placeholder", [False, True])
async def test_later_page_retry_discards_partial_results(*, placeholder: bool) -> None:
    """Restart from the first page without leaking or duplicating old items."""
    api = AFSAPI("http://mock", "0000")
    first = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="name"><c8_array>Old</c8_array></field></item></fsapiResponse>',
    )
    loading = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="50">'
        '<field name="type"><u8>255</u8></field></item><listend/></fsapiResponse>',
    )
    ready = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="name"><c8_array>New</c8_array></field></item><listend/></fsapiResponse>',
    )
    with (
        patch.object(
            api,
            "_AFSAPI__call",
            side_effect=[first, loading if placeholder else FSNodeBlockedError("loading"), ready],
        ) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock),
    ):
        items = await api.get(Nodes.nav_list)
    assert items == [("0", {"name": "New"})]
    assert [args.args[0] for args in call.call_args_list] == [
        "LIST_GET_NEXT/netRemote.nav.list/-1",
        "LIST_GET_NEXT/netRemote.nav.list/49",
        "LIST_GET_NEXT/netRemote.nav.list/-1",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_ready_navigation_list_needs_no_delay(*, empty: bool) -> None:
    """Return normal lists, including genuinely empty folders, immediately."""
    api = AFSAPI("http://mock", "0000")
    response = ElementTree.fromstring(
        "<fsapiResponse><status>FS_OK</status>"
        + ("" if empty else '<item key="0"><field name="type"><u8>0</u8></field></item>')
        + "<listend/></fsapiResponse>",
    )
    with (
        patch.object(api, "_AFSAPI__call", return_value=response) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        items = await api.get(Nodes.nav_list)
    assert items == ([] if empty else [("0", {"type": 0})])
    call.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_nav_list_enables_navigation_only_once() -> None:
    """Readiness retries must not repeat even a successful navigation SET."""
    api = AFSAPI("http://mock", "0000")
    disabled = ElementTree.fromstring(
        "<fsapiResponse><status>FS_OK</status><value><u8>0</u8></value></fsapiResponse>",
    )
    ok = ElementTree.fromstring("<fsapiResponse><status>FS_OK</status><listend/></fsapiResponse>")
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[disabled, ok, FSNodeBlockedError("loading"), ok]) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock),
    ):
        assert [item async for item in api.nav_list()] == []
    assert [args.args[0] for args in call.call_args_list] == [
        "GET/netRemote.nav.state",
        "SET/netRemote.nav.state",
        "LIST_GET_NEXT/netRemote.nav.list/-1",
        "LIST_GET_NEXT/netRemote.nav.list/-1",
    ]


@pytest.mark.asyncio
async def test_blocked_navigation_set_is_not_retried() -> None:
    """A blocked enable command is not a list readiness error."""
    api = AFSAPI("http://mock", "0000")
    disabled = ElementTree.fromstring(
        "<fsapiResponse><status>FS_OK</status><value><u8>0</u8></value></fsapiResponse>",
    )
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[disabled, FSNodeBlockedError("blocked SET")]) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(FSNodeBlockedError, match="blocked SET"),
    ):
        _ = [item async for item in api.nav_list()]
    assert call.call_count == 2  # noqa: PLR2004
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_navigation_list_is_not_retried() -> None:
    """Other list endpoints retain their existing error semantics."""
    api = AFSAPI("http://mock", "0000")
    with (
        patch.object(api, "_AFSAPI__call", side_effect=FSNodeBlockedError("blocked")) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(FSNodeBlockedError),
    ):
        await api.get(Nodes.presets)
    call.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_mixed_readiness_conditions_succeed_on_last_attempt() -> None:
    """Blocked and loading responses share one budget of eight attempts."""
    api = AFSAPI("http://mock", "0000")
    loading = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="type"><u8>255</u8></field></item><listend/></fsapiResponse>',
    )
    ready = ElementTree.fromstring("<fsapiResponse><status>FS_OK</status><listend/></fsapiResponse>")
    responses = [FSNodeBlockedError("loading"), loading] * 3 + [loading, ready]
    with (
        patch.object(api, "_AFSAPI__call", side_effect=responses) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        assert await api.get(Nodes.nav_list) == []
    assert call.call_count == 8  # noqa: PLR2004
    assert sleep.await_count == 7  # noqa: PLR2004


@pytest.mark.asyncio
async def test_ready_multi_page_list_preserves_order() -> None:
    """Normal pagination and key ordering remain unchanged."""
    api = AFSAPI("http://mock", "0000")
    first = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="0">'
        '<field name="name"><c8_array>First</c8_array></field></item></fsapiResponse>',
    )
    last = ElementTree.fromstring(
        '<fsapiResponse><status>FS_OK</status><item key="50">'
        '<field name="name"><c8_array>Last</c8_array></field></item><listend/></fsapiResponse>',
    )
    with (
        patch.object(api, "_AFSAPI__call", side_effect=[first, last]),
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        assert await api.get(Nodes.nav_list) == [("0", {"name": "First"}), ("50", {"name": "Last"})]
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_out_of_range_still_ends_list() -> None:
    """The existing out-of-range termination is not a readiness failure."""
    api = AFSAPI("http://mock", "0000")
    with (
        patch.object(api, "_AFSAPI__call", side_effect=OutOfRangeError("end")) as call,
        patch("afsapi.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        assert await api.get(Nodes.nav_list) == []
    call.assert_awaited_once()
    sleep.assert_not_awaited()
