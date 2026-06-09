from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any


@dataclass(frozen=True)
class DeliveryFile:
    filename: str
    content: bytes


def parse_json_delivery(value: Any) -> Any | None:
    text = str(value or "").strip()
    if not text or text[0] not in "[{":
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def build_json_delivery_file(purchase: dict[str, Any]) -> DeliveryFile | None:
    parsed = parse_json_delivery(purchase.get("value"))
    if parsed is None:
        return None

    unique_id = purchase.get("unique_id") or purchase.get("bought_id") or "delivery"
    filename = _delivery_filename(str(purchase.get("item_name") or "item"), str(unique_id), ".json")
    content = json.dumps(parsed, ensure_ascii=False, indent=2).encode("utf-8")
    return DeliveryFile(filename=filename, content=content)


def build_json_delivery_package(purchases: list[dict[str, Any]]) -> DeliveryFile | None:
    files = [file for purchase in purchases if (file := build_json_delivery_file(purchase))]
    if not files:
        return None
    if len(files) == 1:
        return files[0]

    buffer = BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, file in enumerate(files, 1):
            filename = _unique_zip_name(file.filename, used_names, index)
            archive.writestr(filename, file.content)

    return DeliveryFile(filename="deliveries.zip", content=buffer.getvalue())


async def send_json_delivery_package(
    bot: Any,
    chat_id: int,
    purchases: list[dict[str, Any]],
    *,
    caption: str | None = None,
) -> bool:
    package = build_json_delivery_package(purchases)
    if package is None:
        return False

    from aiogram.types import BufferedInputFile

    await bot.send_document(
        chat_id=chat_id,
        document=BufferedInputFile(package.content, filename=package.filename),
        caption=caption,
    )
    return True


def _delivery_filename(item_name: str, unique_id: str, suffix: str) -> str:
    safe_item = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", item_name).strip(" ._")
    safe_item = re.sub(r"\s+", "_", safe_item)[:60] or "item"
    safe_id = re.sub(r"\D+", "", unique_id)[:24] or "delivery"
    return f"{safe_item}_{safe_id}{suffix}"


def _unique_zip_name(filename: str, used_names: set[str], index: int) -> str:
    if filename not in used_names:
        used_names.add(filename)
        return filename
    stem, dot, suffix = filename.rpartition(".")
    next_name = f"{stem or 'delivery'}_{index}{dot}{suffix}" if dot else f"{filename}_{index}"
    used_names.add(next_name)
    return next_name
