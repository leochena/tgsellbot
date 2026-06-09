from bot.misc.stock_format import (
    format_stock_value_for_delivery,
    stock_values_from_input,
)


def test_plain_text_stock_still_splits_by_line():
    values, skipped_empty, skipped_duplicate = stock_values_from_input("code-a\n\ncode-b\ncode-a")

    assert values == ["code-a", "code-b"]
    assert skipped_empty == 1
    assert skipped_duplicate == 1


def test_json_array_stock_imports_multiple_items():
    values, skipped_empty, skipped_duplicate = stock_values_from_input(
        '[{"account":"a@example.com","password":"p1"},{"account":"b@example.com","password":"p2"}]'
    )

    assert values == [
        '{"account":"a@example.com","password":"p1"}',
        '{"account":"b@example.com","password":"p2"}',
    ]
    assert skipped_empty == 0
    assert skipped_duplicate == 0


def test_json_object_with_values_array_imports_multiple_items():
    values, skipped_empty, skipped_duplicate = stock_values_from_input(
        '{"values":["code-a","code-b","code-a",""]}'
    )

    assert values == ["code-a", "code-b"]
    assert skipped_empty == 1
    assert skipped_duplicate == 1


def test_json_object_stock_imports_as_one_structured_item():
    values, skipped_empty, skipped_duplicate = stock_values_from_input(
        '{"account":"a@example.com","password":"p1"}'
    )

    assert values == ['{"account":"a@example.com","password":"p1"}']
    assert skipped_empty == 0
    assert skipped_duplicate == 0


def test_json_stock_delivery_is_human_readable():
    text = format_stock_value_for_delivery('{"account":"a@example.com","password":"p1"}')

    assert text == "account: a@example.com\npassword: p1"


def test_plain_delivery_value_is_unchanged():
    assert format_stock_value_for_delivery("code-a") == "code-a"
