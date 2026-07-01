"""Unit tests for extracted list handler methods."""

import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
from afsapi.api import AFSAPI
from defusedxml import ElementTree as DefusedET


def test_parse_field_value() -> None:
    """Test the static _parse_field_value method handles different tags properly."""
    assert AFSAPI._parse_field_value("c8_array", "test") == "test" # noqa: SLF001
    assert AFSAPI._parse_field_value("array", "another") == "another" # noqa: SLF001
    assert AFSAPI._parse_field_value("u8", "123") == 123 # noqa: PLR2004, SLF001
    assert AFSAPI._parse_field_value("s16", "-45") == -45 # noqa: PLR2004, SLF001
    assert AFSAPI._parse_field_value("e8", "2") == 2 # noqa: PLR2004, SLF001
    assert AFSAPI._parse_field_value("unknown", "value") == "value" # noqa: SLF001

def test_handle_item() -> None:
    """Test the static _handle_item method properly parses an XML item."""
    xml_data = """
    <item key="5">
        <field name="title">
            <c8_array>Song</c8_array>
        </field>
        <field name="id">
            <u32>999</u32>
        </field>
    </item>
    """
    element = DefusedET.fromstring(xml_data)
    key, data = AFSAPI._handle_item(element) # noqa: SLF001
    assert key == "5"
    assert data["title"] == "Song"
    assert data["id"] == 999 # noqa: PLR2004

@pytest.mark.asyncio
async def test_get_next_items() -> None:
    """Test the _get_next_items method reads and parses list nodes."""
    api = AFSAPI("http://mock", "1234")

    async def mock_call(path: str, params: dict, **kwargs: dict) -> ET.Element: # noqa: ARG001
        if path == "LIST_GET_NEXT/test_list/-1":
            xml_response = """
            <fsapiResponse>
                <status>FS_OK</status>
                <item key="1"><field name="foo"><c8_array>bar</c8_array></field></item>
                <listend/>
            </fsapiResponse>
            """
            return DefusedET.fromstring(xml_response)
        raise ValueError("Unexpected path") # noqa: TRY003, EM101

    with patch.object(api, "_AFSAPI__call", side_effect=mock_call):
        items, has_ended = await api._get_next_items("test_list", -1, 10) # noqa: SLF001
        assert len(items) == 1
        assert has_ended is True
