from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


JSON_STOCK_KEYS = ("items", "stock", "values", "data")


def stock_values_from_input(raw: Any, *, max_lines: int = 1000) -> tuple[list[str], int, int]:
    if raw is None:
        raw_values: list[Any] = []
    elif isinstance(raw, str):
        raw_values = _values_from_string(raw)
    elif isinstance(raw, Mapping):
        raw_values = _values_from_mapping(raw)
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, str)):
        raw_values = list(raw)
    else:
        raw_values = [raw]

    if len(raw_values) > max_lines:
        raise ValueError(f"单次最多提交 {max_lines} 条库存。")

    values: list[str] = []
    seen: set[str] = set()
    skipped_empty = 0
    skipped_duplicate = 0

    for raw_value in raw_values:
        value = normalize_stock_value(raw_value)
        if not value:
            skipped_empty += 1
            continue
        if value in seen:
            skipped_duplicate += 1
            continue
        seen.add(value)
        values.append(value)

    return values, skipped_empty, skipped_duplicate


def normalize_stock_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value).strip()


def format_stock_value_for_delivery(value: Any) -> str:
    text = str(value or "").strip()
    parsed = _try_json(text)
    if parsed is None:
        return text
    return _format_json_delivery(parsed)


def _values_from_string(raw: str) -> list[Any]:
    text = raw.strip()
    if not text:
        return []

    parsed = _try_json(text)
    if parsed is None:
        return raw.splitlines()
    return _values_from_json(parsed)


def _values_from_json(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        extracted = _values_from_mapping(value)
        return extracted if extracted != [value] else [value]
    return [value]


def _values_from_mapping(value: Mapping[str, Any]) -> list[Any]:
    for key in JSON_STOCK_KEYS:
        nested = value.get(key)
        if isinstance(nested, list):
            return nested
    return [dict(value)]


def _try_json(text: str) -> Any | None:
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def _format_json_delivery(value: Any) -> str:
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in value.items():
            lines.append(f"{key}: {_format_json_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        return "\n".join(f"{index}. {_format_json_scalar(item)}" for index, item in enumerate(value, 1))
    return _format_json_scalar(value)


def _format_json_scalar(value: Any) -> str:
    if isinstance(value, (Mapping, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value)
