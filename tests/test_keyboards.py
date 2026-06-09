from bot.keyboards.inline import (
    main_menu, profile_keyboard, simple_buttons, back, close, item_info, payment_menu,
    get_payment_choice, question_buttons, check_sub, referral_system_keyboard,
    admin_console_keyboard, lottery_admin_keyboard, lottery_keyboard,
    language_keyboard,
)


def _all_callback_data(markup):
    """Extract all callback_data values from markup."""
    result = []
    for row in markup.inline_keyboard:
        for btn in row:
            if btn.callback_data:
                result.append(btn.callback_data)
    return result


def _all_button_texts(markup):
    """Extract all button texts from markup."""
    result = []
    for row in markup.inline_keyboard:
        for btn in row:
            result.append(btn.text)
    return result


def _has_url_button(markup):
    """Check if any button has a URL."""
    for row in markup.inline_keyboard:
        for btn in row:
            if btn.url:
                return True
    return False


class TestMainMenu:

    def test_basic_buttons_present(self):
        markup = main_menu(role=1)
        cbs = _all_callback_data(markup)
        assert "shop" in cbs
        assert "rules" in cbs
        assert "checkin" in cbs
        assert "lottery" in cbs
        assert "profile" in cbs
        assert "cart" in cbs
        assert "redeem_balance_promo" in cbs
        assert "language_settings" in cbs

    def test_no_admin_for_regular_user(self):
        markup = main_menu(role=1)
        cbs = _all_callback_data(markup)
        assert "console" not in cbs

    def test_admin_button_for_admin(self):
        markup = main_menu(role=2)
        cbs = _all_callback_data(markup)
        assert "console" in cbs

    def test_channel_button(self):
        markup = main_menu(role=1, channel="test_channel")
        cbs = _all_callback_data(markup)
        assert "group_invite_link" in cbs

    def test_group_invite_button_is_tracked_callback(self):
        markup = main_menu(role=1, channel="https://t.me/gpt_free_plus_team")
        cbs = _all_callback_data(markup)
        assert "group_invite_link" in cbs
        assert not _has_url_button(markup)

    def test_helper_button(self):
        markup = main_menu(role=1, helper="12345")
        assert _has_url_button(markup)

    def test_no_channel_no_helper(self):
        markup = main_menu(role=1)
        assert not _has_url_button(markup)


class TestProfileKeyboard:

    def test_replenish_always_present(self):
        markup = profile_keyboard(referral_percent=0, user_items=0)
        cbs = _all_callback_data(markup)
        assert "replenish_balance" in cbs

    def test_referral_button_when_percent_nonzero(self):
        markup = profile_keyboard(referral_percent=10)
        cbs = _all_callback_data(markup)
        assert "referral_system" in cbs

    def test_no_referral_button_when_zero(self):
        markup = profile_keyboard(referral_percent=0)
        cbs = _all_callback_data(markup)
        assert "referral_system" not in cbs

    def test_bought_items_when_user_has_items(self):
        markup = profile_keyboard(referral_percent=0, user_items=5)
        cbs = _all_callback_data(markup)
        assert "bought_items" in cbs

    def test_no_bought_items_when_zero(self):
        markup = profile_keyboard(referral_percent=0, user_items=0)
        cbs = _all_callback_data(markup)
        assert "bought_items" not in cbs

    def test_back_button_present(self):
        markup = profile_keyboard(referral_percent=0)
        cbs = _all_callback_data(markup)
        assert "back_to_menu" in cbs

    def test_language_button_present(self):
        markup = profile_keyboard(referral_percent=0)
        cbs = _all_callback_data(markup)
        assert "language_settings" in cbs


class TestLanguageKeyboard:

    def test_language_choices_present(self):
        markup = language_keyboard("en")
        cbs = _all_callback_data(markup)
        assert "set_locale:ru" in cbs
        assert "set_locale:en" in cbs
        assert "set_locale:zh" in cbs
        assert "back_to_menu" in cbs


class TestLotteryKeyboard:

    def test_lottery_keyboard_active_has_checkin(self):
        markup = lottery_keyboard(True)
        cbs = _all_callback_data(markup)
        assert "checkin" in cbs
        assert "back_to_menu" in cbs

    def test_lottery_admin_keyboard_active_has_actions(self):
        markup = lottery_admin_keyboard(1)
        cbs = _all_callback_data(markup)
        assert "lottery_admin_create" in cbs
        assert "lottery_admin_draw:1" in cbs
        assert "lottery_admin_close:1" in cbs


class TestPaymentMenu:

    def test_payment_menu_has_pay_url(self):
        markup = payment_menu("https://example.com/pay")
        has_url = False
        for row in markup.inline_keyboard:
            for btn in row:
                if btn.url == "https://example.com/pay":
                    has_url = True
        assert has_url

    def test_payment_menu_has_check(self):
        markup = payment_menu("https://example.com/pay")
        cbs = _all_callback_data(markup)
        assert "check" in cbs


class TestItemInfoKeyboard:

    def test_has_buy_and_back(self):
        markup = item_info("Widget", "gp_0")
        cbs = _all_callback_data(markup)
        assert "buy" in cbs
        assert "add_to_cart" in cbs
        assert "cart" in cbs
        assert "gp_0" in cbs

    def test_out_of_stock_hides_purchase_actions(self):
        markup = item_info("Widget", "gp_0", in_stock=False)
        cbs = _all_callback_data(markup)
        assert "buy" not in cbs
        assert "add_to_cart" not in cbs
        assert "cart" in cbs
        assert "noop" in cbs

    def test_points_price_adds_redeem_button(self):
        markup = item_info("Widget", "gp_0", points_price=10)
        cbs = _all_callback_data(markup)
        assert "buy" in cbs
        assert "redeem_points" in cbs

    def test_points_redeem_limit_uses_quantity_picker(self):
        markup = item_info("Widget", "gp_0", points_price=10, points_max_per_redeem=3)
        cbs = _all_callback_data(markup)
        assert "redeem_points_choose" in cbs
        assert "redeem_points" not in cbs


class TestSimpleButtons:

    def test_creates_buttons(self):
        markup = simple_buttons([("A", "a"), ("B", "b")])
        cbs = _all_callback_data(markup)
        assert "a" in cbs
        assert "b" in cbs

    def test_button_count(self):
        markup = simple_buttons([("A", "a"), ("B", "b"), ("C", "c")])
        total = sum(len(row) for row in markup.inline_keyboard)
        assert total == 3


class TestBackAndClose:

    def test_back_default(self):
        markup = back()
        cbs = _all_callback_data(markup)
        assert "menu" in cbs

    def test_back_custom_cb(self):
        markup = back("profile")
        cbs = _all_callback_data(markup)
        assert "profile" in cbs

    def test_close_button(self):
        markup = close()
        cbs = _all_callback_data(markup)
        assert "close" in cbs


class TestReferralSystemKeyboard:

    def test_no_referrals_no_earnings(self):
        markup = referral_system_keyboard(has_referrals=False, has_earnings=False)
        cbs = _all_callback_data(markup)
        assert "view_referrals" not in cbs
        assert "view_all_earnings" not in cbs
        assert "profile" in cbs  # back button

    def test_with_referrals(self):
        markup = referral_system_keyboard(has_referrals=True, has_earnings=False)
        cbs = _all_callback_data(markup)
        assert "view_referrals" in cbs

    def test_with_earnings(self):
        markup = referral_system_keyboard(has_referrals=False, has_earnings=True)
        cbs = _all_callback_data(markup)
        assert "view_all_earnings" in cbs

    def test_with_both(self):
        markup = referral_system_keyboard(has_referrals=True, has_earnings=True)
        cbs = _all_callback_data(markup)
        assert "view_referrals" in cbs
        assert "view_all_earnings" in cbs


class TestGetPaymentChoice:

    def test_has_all_methods(self):
        markup = get_payment_choice()
        cbs = _all_callback_data(markup)
        assert "pay_cryptopay" in cbs
        assert "pay_stars" in cbs
        assert "pay_fiat" in cbs
        assert "replenish_balance" in cbs  # back


class TestQuestionButtons:

    def test_has_yes_no_back(self):
        markup = question_buttons("confirm_delete", "shop")
        cbs = _all_callback_data(markup)
        assert "confirm_delete_yes" in cbs
        assert "confirm_delete_no" in cbs
        assert "shop" in cbs


class TestCheckSub:

    def test_has_channel_url(self):
        markup = check_sub("test_channel")
        has_url = False
        for row in markup.inline_keyboard:
            for btn in row:
                if btn.url and "test_channel" in btn.url:
                    has_url = True
        assert has_url

    def test_has_check_callback(self):
        markup = check_sub("test_channel")
        cbs = _all_callback_data(markup)
        assert "sub_channel_done" in cbs


class TestAdminConsoleKeyboard:

    def test_has_roles_button(self):
        markup = admin_console_keyboard()
        cbs = _all_callback_data(markup)
        assert "role_mgmt" in cbs

    def test_has_all_admin_buttons(self):
        markup = admin_console_keyboard()
        cbs = _all_callback_data(markup)
        assert "shop_management" in cbs
        assert "goods_management" in cbs
        assert "categories_management" in cbs
        assert "user_management" in cbs
        assert "send_message" in cbs
        assert "role_mgmt" in cbs

    def test_maintenance_toggle(self):
        markup_on = admin_console_keyboard(maintenance_mode=True)
        markup_off = admin_console_keyboard(maintenance_mode=False)
        texts_on = _all_button_texts(markup_on)
        texts_off = _all_button_texts(markup_off)
        # The maintenance button text should differ between states
        assert texts_on != texts_off
