import json
import zipfile
from io import BytesIO

import pytest

from bot.misc.delivery_files import (
    build_json_delivery_file,
    build_json_delivery_package,
    parse_json_delivery,
    send_json_delivery_package,
)


def test_plain_text_is_not_json_delivery():
    assert parse_json_delivery("plain-code") is None
    assert build_json_delivery_file({"item_name": "卡密", "value": "plain-code"}) is None


def test_single_json_delivery_file():
    file = build_json_delivery_file({
        "item_name": "OpenAI 账号",
        "unique_id": 12345,
        "value": '{"account":"a@example.com","password":"p1"}',
    })

    assert file is not None
    assert file.filename == "OpenAI_账号_12345.json"
    assert json.loads(file.content.decode("utf-8")) == {
        "account": "a@example.com",
        "password": "p1",
    }


def test_multiple_json_delivery_package_is_zip():
    package = build_json_delivery_package([
        {"item_name": "A", "unique_id": 1, "value": '{"code":"a"}'},
        {"item_name": "B", "unique_id": 2, "value": '{"code":"b"}'},
        {"item_name": "Text", "unique_id": 3, "value": "plain"},
    ])

    assert package is not None
    assert package.filename == "deliveries.zip"
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        assert sorted(archive.namelist()) == ["A_1.json", "B_2.json"]
        assert json.loads(archive.read("A_1.json").decode("utf-8")) == {"code": "a"}


@pytest.mark.asyncio
async def test_send_json_delivery_package_sends_document(mock_bot):
    sent = await send_json_delivery_package(
        mock_bot,
        100001,
        [{"item_name": "A", "unique_id": 1, "value": '{"code":"a"}'}],
        caption="caption",
    )

    assert sent is True
    mock_bot.send_document.assert_awaited_once()
    kwargs = mock_bot.send_document.await_args.kwargs
    assert kwargs["chat_id"] == 100001
    assert kwargs["caption"] == "caption"


@pytest.mark.asyncio
async def test_send_json_delivery_package_skips_plain_text(mock_bot):
    sent = await send_json_delivery_package(
        mock_bot,
        100001,
        [{"item_name": "A", "unique_id": 1, "value": "plain"}],
    )

    assert sent is False
    mock_bot.send_document.assert_not_called()
