import pytest
from unittest.mock import patch
from aiogram.enums.chat_type import ChatType

from bot.database.methods.read import check_user, select_max_role_id


class TestStartHandler:

    async def test_start_creates_new_user(self, make_message, fsm_context):
        from bot.handlers.user.main import start

        msg = make_message(text="/start", user_id=300001)
        msg.chat.type = ChatType.PRIVATE

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.OWNER_ID = 999999
            env.CHANNEL_URL = ""
            env.HELPER_ID = ""
            env.RULES = ""
            await start(msg, fsm_context)

        user = await check_user(300001)
        assert user is not None
        assert user['telegram_id'] == 300001

    async def test_start_with_referral(self, make_message, fsm_context, user_factory):
        from bot.handlers.user.main import start

        # Create referrer first
        await user_factory(telegram_id=300010)

        msg = make_message(text="/start 300010", user_id=300011)
        msg.chat.type = ChatType.PRIVATE

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.OWNER_ID = 999999
            env.CHANNEL_URL = ""
            env.HELPER_ID = ""
            env.RULES = ""
            await start(msg, fsm_context)

        user = await check_user(300011)
        assert user is not None
        assert user['referral_id'] == 300010

    async def test_start_self_referral_ignored(self, make_message, fsm_context):
        from bot.handlers.user.main import start

        msg = make_message(text="/start 300020", user_id=300020)
        msg.chat.type = ChatType.PRIVATE

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.OWNER_ID = 999999
            env.CHANNEL_URL = ""
            env.HELPER_ID = ""
            env.RULES = ""
            await start(msg, fsm_context)

        user = await check_user(300020)
        assert user is not None
        assert user['referral_id'] is None

    async def test_start_owner_gets_max_role(self, make_message, fsm_context):
        from bot.handlers.user.main import start

        msg = make_message(text="/start", user_id=300030)
        msg.chat.type = ChatType.PRIVATE

        max_role = await select_max_role_id()
        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.OWNER_ID = 300030
            env.CHANNEL_URL = ""
            env.HELPER_ID = ""
            env.RULES = ""
            await start(msg, fsm_context)

        user = await check_user(300030)
        assert user['role_id'] == max_role

    async def test_start_non_private_ignored(self, make_message, fsm_context):
        from bot.handlers.user.main import start

        msg = make_message(text="/start", user_id=300040)
        msg.chat.type = ChatType.GROUP

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.OWNER_ID = 999999
            await start(msg, fsm_context)

        # User should NOT be created
        user = await check_user(300040)
        assert user is None


class TestProfileHandler:

    async def test_profile_shows_balance(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.main import profile_callback_handler

        await user_factory(telegram_id=300050, balance=500)

        call = make_callback_query(data="profile", user_id=300050)

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.PAY_CURRENCY = "RUB"
            env.BALANCE_CURRENCY = "UStars"
            env.REFERRAL_PERCENT = 0
            await profile_callback_handler(call, fsm_context)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "500" in str(text)

    async def test_language_settings_shows_choices(self, make_callback_query, fsm_context, user_factory):
        from bot.handlers.user.main import language_settings_callback_handler

        await user_factory(telegram_id=300051)
        call = make_callback_query(data="language_settings", user_id=300051)

        await language_settings_callback_handler(call, fsm_context)

        call.message.edit_text.assert_called_once()
        markup = call.message.edit_text.call_args.kwargs["reply_markup"]
        callback_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "set_locale:en" in callback_data

    async def test_set_locale_updates_user(self, make_callback_query, fsm_context, user_factory):
        from bot.database.methods.read import check_user
        from bot.handlers.user.main import set_locale_callback_handler

        await user_factory(telegram_id=300052)
        call = make_callback_query(data="set_locale:en", user_id=300052)

        await set_locale_callback_handler(call, fsm_context)

        user = await check_user(300052)
        assert user["locale"] == "en"
        call.answer.assert_called_once()
        call.message.edit_text.assert_called_once()


class TestRulesHandler:

    async def test_rules_with_text(self, make_callback_query, fsm_context):
        from bot.handlers.user.main import rules_callback_handler

        call = make_callback_query(data="rules", user_id=300060)

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.RULES = "Shop rules text here"
            env.PAY_CURRENCY = "USD"
            env.BALANCE_CURRENCY = "UStars"
            env.STARS_PER_VALUE = 0.91
            await rules_callback_handler(call, fsm_context)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "Shop rules text here" in text
        assert "UStars" in text

    async def test_rules_not_set(self, make_callback_query, fsm_context):
        from bot.handlers.user.main import rules_callback_handler

        call = make_callback_query(data="rules", user_id=300070)

        with patch('bot.handlers.user.main.EnvKeys') as env:
            env.RULES = ""
            env.PAY_CURRENCY = "USD"
            env.BALANCE_CURRENCY = "UStars"
            env.STARS_PER_VALUE = 0.91
            await rules_callback_handler(call, fsm_context)

        call.message.edit_text.assert_called_once()
        text = call.message.edit_text.call_args[0][0]
        assert "UStars" in text
        assert "0.91" in text
        assert "USD" in text
        call.answer.assert_not_called()


class TestChatIdHandler:

    async def test_chatid_owner_gets_group_chat_id(self, make_message):
        from bot.handlers.user.main import chatid

        msg = make_message(text="/chatid", user_id=999999)
        msg.chat.id = -1001234567890
        msg.chat.type = "supergroup"

        await chatid(msg)

        msg.answer.assert_awaited_once()
        assert "chatid.response" in msg.answer.await_args.args[0]

    async def test_chatid_non_owner_ignored(self, make_message):
        from bot.handlers.user.main import chatid

        msg = make_message(text="/chatid", user_id=123456)
        msg.chat.id = -1001234567890
        msg.chat.type = "supergroup"

        await chatid(msg)

        msg.answer.assert_not_called()
