import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from bot.database import Database
from bot.database.models import BoughtGoods, CartItems, Goods
from bot.database.models.main import PromoCodes


@pytest.fixture(autouse=True)
def mock_client_audit():
    with patch("bot.web.client.log_audit", new_callable=AsyncMock):
        yield


class TestWebClientCatalog:
    async def test_create_category_and_snapshot(self):
        from bot.web.client import catalog_snapshot, create_category_record

        result = await create_category_record({"name": "账号"})
        assert result["category"]["name"] == "账号"

        snapshot = await catalog_snapshot()
        assert snapshot["stats"]["categories"] == 1
        assert snapshot["categories"][0]["name"] == "账号"

    async def test_create_product_with_stock_and_duplicate_batch_values(self):
        from bot.web.client import (
            catalog_snapshot,
            create_category_record,
            create_product_record,
        )

        category = (await create_category_record({"name": "会员"}))["category"]
        result = await create_product_record({
            "name": "月卡",
            "description": "30 天",
            "price": "19.9",
            "points_price": "80",
            "points_max_per_redeem": "3",
            "lottery_enabled": True,
            "lottery_level": "一等奖",
            "lottery_winners_count": "2",
            "category_id": category["id"],
            "stock_values": "code-a\ncode-b\ncode-a\n\n",
        })

        assert result["product"]["name"] == "月卡"
        assert result["product"]["price"] == "19.90"
        assert result["product"]["points_price"] == 80
        assert result["product"]["points_max_per_redeem"] == 3
        assert result["product"]["lottery_enabled"] is True
        assert result["product"]["lottery_level"] == "一等奖"
        assert result["product"]["lottery_winners_count"] == 2
        assert result["stock"] == {
            "added": 2,
            "skipped_empty": 1,
            "skipped_duplicate": 1,
            "skipped_extra_infinite": 0,
        }

        snapshot = await catalog_snapshot()
        assert snapshot["stats"]["products"] == 1
        assert snapshot["stats"]["stock_values"] == 2
        assert snapshot["products"][0]["stock_count"] == 2
        assert snapshot["products"][0]["points_price"] == 80
        assert snapshot["products"][0]["points_max_per_redeem"] == 3
        assert snapshot["products"][0]["lottery_enabled"] is True

    async def test_add_stock_skips_existing_values_and_preview_masks_values(self):
        from bot.web.client import (
            add_stock_record,
            create_category_record,
            create_product_record,
            stock_preview,
        )

        category = (await create_category_record({"name": "软件"}))["category"]
        product = (await create_product_record({
            "name": "激活码",
            "description": "",
            "price": 5,
            "category_id": category["id"],
            "stock_values": "secret-code-0001",
        }))["product"]

        result = await add_stock_record(product["id"], {
            "stock_values": "secret-code-0001\nsecret-code-0002\nsecret-code-0002\n",
        })
        assert result["stock"]["added"] == 1
        assert result["stock"]["skipped_existing"] == 1
        assert result["stock"]["skipped_duplicate"] == 1

        preview = await stock_preview(product["id"])
        assert preview["total"] == 2
        assert preview["items"][0]["value_masked"] == "secr...0001"
        assert "secret-code-0001" not in preview["items"][0]["value_masked"]

    async def test_infinite_product_rejects_add_stock(self):
        from bot.web.client import (
            ClientError,
            add_stock_record,
            create_category_record,
            create_product_record,
        )

        category = (await create_category_record({"name": "无限"}))["category"]
        product = (await create_product_record({
            "name": "教程",
            "description": "固定链接",
            "price": 1,
            "category_id": category["id"],
            "is_infinity": True,
            "stock_values": "https://example.test/course",
        }))["product"]

        with pytest.raises(ClientError, match="无限库存商品不能追加普通库存"):
            await add_stock_record(product["id"], {"stock_values": "another"})

    async def test_create_product_accepts_json_stock_values(self):
        from bot.web.client import (
            catalog_snapshot,
            create_category_record,
            create_product_record,
        )

        category = (await create_category_record({"name": "账号"}))["category"]
        result = await create_product_record({
            "name": "成品号",
            "description": "JSON 库存",
            "price": "29.9",
            "category_id": category["id"],
            "stock_values": {
                "items": [
                    {"account": "a@example.com", "password": "p1"},
                    {"account": "b@example.com", "password": "p2"},
                ]
            },
        })

        assert result["stock"]["added"] == 2
        snapshot = await catalog_snapshot()
        assert snapshot["stats"]["stock_values"] == 2

    async def test_add_stock_accepts_json_array(self):
        from bot.web.client import (
            add_stock_record,
            create_category_record,
            create_product_record,
            stock_preview,
        )

        category = (await create_category_record({"name": "兑换码"}))["category"]
        product = (await create_product_record({
            "name": "礼品卡",
            "description": "",
            "price": 10,
            "category_id": category["id"],
        }))["product"]

        result = await add_stock_record(product["id"], {
            "stock_values": '["code-a", "code-b", "code-a", ""]',
        })

        assert result["stock"]["added"] == 2
        assert result["stock"]["skipped_duplicate"] == 1
        assert result["stock"]["skipped_empty"] == 1
        assert (await stock_preview(product["id"]))["total"] == 2

    async def test_create_product_accepts_multi_file_json_array_payload(self):
        from bot.web.client import (
            catalog_snapshot,
            create_category_record,
            create_product_record,
        )

        category = (await create_category_record({"name": "多文件"}))["category"]
        result = await create_product_record({
            "name": "批量 JSON",
            "description": "多个 JSON 文件合并后的库存",
            "price": "3.5",
            "category_id": category["id"],
            "stock_values": (
                '[{"account":"a@example.com","password":"p1"},'
                '{"account":"b@example.com","password":"p2"},'
                '{"token":"c"}]'
            ),
        })

        assert result["stock"]["added"] == 3
        snapshot = await catalog_snapshot()
        assert snapshot["stats"]["stock_values"] == 3

    async def test_create_product_accepts_large_json_stock_values(self):
        from bot.web.client import (
            catalog_snapshot,
            create_category_record,
            create_product_record,
        )

        large_token = "x" * 5000
        category = (await create_category_record({"name": "大 JSON"}))["category"]
        result = await create_product_record({
            "name": "大库存",
            "description": "长 JSON 库存",
            "price": "2",
            "category_id": category["id"],
            "stock_values": [
                {"account": "a@example.com", "access_token": large_token},
                {"account": "b@example.com", "access_token": large_token},
            ],
        })

        assert result["stock"]["added"] == 2
        snapshot = await catalog_snapshot()
        assert snapshot["stats"]["stock_values"] == 2

    async def test_client_html_allows_multiple_json_files(self):
        from bot.web.client import CLIENT_HTML, _client_html

        assert 'id="productJsonFile" type="file" accept=".json,application/json" multiple' in CLIENT_HTML
        assert 'id="editJsonFile" type="file" accept=".json,application/json" multiple' in CLIENT_HTML
        assert 'id="stockJsonFile" type="file" accept=".json,application/json" multiple' in CLIENT_HTML
        assert 'name="points_price"' in CLIENT_HTML
        assert 'name="points_max_per_redeem"' in CLIENT_HTML
        assert 'name="lottery_enabled"' in CLIENT_HTML
        assert 'name="lottery_level"' in CLIENT_HTML
        assert 'name="lottery_winners_count"' in CLIENT_HTML
        assert 'id="editPointsPrice"' in CLIENT_HTML
        assert 'id="editPointsMaxPerRedeem"' in CLIENT_HTML
        assert 'id="editLotteryEnabled"' in CLIENT_HTML
        assert "jsonStockItemsFromValue" in CLIENT_HTML
        assert "JSON.stringify(importedValues, null, 2)" in CLIENT_HTML
        assert "余额价格（__BALANCE_CURRENCY__）" in CLIENT_HTML
        assert "该奖项中奖人数" in CLIENT_HTML
        assert "Telegram 商店后台 · 商品运营" in CLIENT_HTML
        assert "TGSellBot 运营客户端" not in CLIENT_HTML

        with patch("bot.web.client.EnvKeys") as env:
            env.BALANCE_CURRENCY = "UStars"
            env.PAY_CURRENCY = "USD"
            env.STARS_PER_VALUE = 0.91
            html = _client_html()

        assert "余额价格（UStars）" in html
        assert "不是真实 USD" in html
        assert "1 UStars = 0.91" in html
        assert "font-size: 12pt;" in html
        assert "font: 1rem/1.45" in html

        large_html = _client_html(font_size=18)
        assert "font-size: 18pt;" in large_html

    async def test_client_forms_keep_target_before_async_reset(self):
        from bot.web.client import CLIENT_HTML

        assert "const target = event.currentTarget;" in CLIENT_HTML
        assert "new FormData(target)" in CLIENT_HTML
        assert "target.reset();" in CLIENT_HTML
        assert "event.currentTarget.reset();" not in CLIENT_HTML

    async def test_client_html_includes_promo_management(self):
        from bot.web.client import CLIENT_HTML

        assert 'id="promoSection"' in CLIENT_HTML
        assert 'id="promoForm"' in CLIENT_HTML
        assert "余额兑换码在机器人首页兑换" in CLIENT_HTML
        assert "商品折扣码在商品详情页使用" in CLIENT_HTML
        assert '/admin/api/promos' in CLIENT_HTML
        assert '/client/api/promos' not in CLIENT_HTML
        assert 'id="mPromos"' in CLIENT_HTML

    async def test_old_client_entry_redirects_to_admin_operations(self):
        from starlette.requests import Request
        from bot.web.client import client_home, client_page, client_routes

        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/client",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
            "session": {},
        })

        client_response = await client_page(request)
        home_response = await client_home(request)

        assert client_response.status_code == 302
        assert client_response.headers["location"] == "/admin/operations"
        assert home_response.status_code == 302
        assert home_response.headers["location"] == "/admin/operations"
        assert not any(getattr(route, "path", "").startswith("/client/api") for route in client_routes)

    async def test_create_balance_promo_from_client(self):
        from bot.web.client import create_promo_record, promo_snapshot

        result = await create_promo_record({
            "code": "gift-50",
            "discount_type": "balance",
            "discount_value": "50",
            "max_uses": "3",
            "is_active": True,
            "category_id": "999",
            "item_id": "999",
        })

        assert result["promo"]["code"] == "GIFT-50"
        assert result["promo"]["discount_type"] == "balance"
        assert result["promo"]["category_id"] is None
        assert result["promo"]["item_id"] is None

        snapshot = await promo_snapshot()
        assert snapshot["stats"]["promos"] == 1
        assert snapshot["stats"]["balance"] == 1
        assert snapshot["promos"][0]["discount_type_label"] == "余额兑换码"

    async def test_create_product_discount_promo_bound_to_item(self):
        from bot.web.client import (
            create_category_record,
            create_product_record,
            create_promo_record,
            promo_snapshot,
        )

        category = (await create_category_record({"name": "会员"}))["category"]
        product = (await create_product_record({
            "name": "月卡",
            "description": "",
            "price": "20",
            "category_id": category["id"],
            "stock_values": "code-a",
        }))["product"]

        result = await create_promo_record({
            "code": "off10",
            "discount_type": "percent",
            "discount_value": "10",
            "max_uses": "5",
            "item_id": product["id"],
        })

        assert result["promo"]["code"] == "OFF10"
        assert result["promo"]["discount_type"] == "percent"
        assert result["promo"]["item_id"] == product["id"]
        assert result["promo"]["item_name"] == "月卡"

        snapshot = await promo_snapshot()
        assert snapshot["stats"]["product"] == 1
        assert snapshot["promos"][0]["item_name"] == "月卡"

    async def test_toggle_and_delete_promo_from_client(self):
        from bot.web.client import (
            create_promo_record,
            delete_promo_record,
            promo_snapshot,
            toggle_promo_record,
        )

        promo = (await create_promo_record({
            "code": "toggle-me",
            "discount_type": "balance",
            "discount_value": "1",
        }))["promo"]

        toggled = await toggle_promo_record(promo["id"])
        assert toggled["promo"]["is_active"] is False
        assert (await promo_snapshot())["stats"]["active"] == 0

        deleted = await delete_promo_record(promo["id"])
        assert deleted["deleted"] is True
        assert (await promo_snapshot())["stats"]["promos"] == 0

    async def test_balance_promo_lookup_is_case_insensitive_for_manual_codes(self, user_factory):
        from bot.database.methods.transactions import redeem_balance_promo

        await user_factory(telegram_id=333002, balance=0)
        async with Database().session() as s:
            s.add(PromoCodes(
                code="mixedCase42",
                discount_type="balance",
                discount_value=Decimal("7.00"),
                max_uses=1,
                is_active=True,
            ))

        success, error_key, amount = await redeem_balance_promo("MIXEDCASE42", 333002)
        assert success is True
        assert error_key == ""
        assert amount == Decimal("7.00")

    async def test_update_product_renames_cart_and_purchase_references(self, user_factory):
        from bot.web.client import (
            create_category_record,
            create_product_record,
            update_product_record,
        )

        await user_factory(telegram_id=333001, balance=100)
        category = (await create_category_record({"name": "服务"}))["category"]
        product = (await create_product_record({
            "name": "旧名称",
            "description": "old",
            "price": "10",
            "category_id": category["id"],
            "stock_values": "value-one",
        }))["product"]

        async with Database().session() as s:
            s.add(CartItems(user_id=333001, item_name="旧名称"))
            s.add(BoughtGoods(
                name="旧名称",
                value="delivered",
                price=Decimal("10"),
                buyer_id=333001,
                bought_datetime=datetime.datetime.now(datetime.timezone.utc),
                unique_id=123456789,
            ))

        await update_product_record(product["id"], {
            "name": "新名称",
            "description": "new",
            "price": "12.5",
            "points_price": "15",
            "points_max_per_redeem": "4",
            "lottery_enabled": True,
            "lottery_level": "二等奖",
            "lottery_winners_count": "3",
            "category_id": category["id"],
            "is_infinity": False,
        })

        async with Database().session() as s:
            goods = (await s.execute(select(Goods).where(Goods.id == product["id"]))).scalars().one()
            cart = (await s.execute(select(CartItems).where(CartItems.user_id == 333001))).scalars().one()
            bought = (await s.execute(select(BoughtGoods).where(BoughtGoods.buyer_id == 333001))).scalars().one()

        assert goods.name == "新名称"
        assert goods.price == Decimal("12.50")
        assert goods.points_price == 15
        assert goods.points_max_per_redeem == 4
        assert goods.lottery_enabled is True
        assert goods.lottery_level == "二等奖"
        assert goods.lottery_winners_count == 3
        assert cart.item_name == "新名称"
        assert bought.item_name == "新名称"
