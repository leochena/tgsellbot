from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", encoding="utf-8")


@dataclass(frozen=True)
class CatalogRow:
    category: str
    name: str
    description: str
    price: Decimal
    value: str
    is_infinity: bool


def parse_bool(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError("is_infinity must be true/false")


def load_rows(path: Path) -> list[CatalogRow]:
    required = {"category", "name", "description", "price", "value", "is_infinity"}
    rows: list[CatalogRow] = []
    product_defs: dict[str, tuple[str, str, Decimal]] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing CSV columns: {', '.join(sorted(missing))}")

        for line_no, raw in enumerate(reader, start=2):
            try:
                category = (raw["category"] or "").strip()
                name = (raw["name"] or "").strip()
                description = (raw["description"] or "").strip()
                value = (raw["value"] or "").strip()
                price = Decimal((raw["price"] or "").strip()).quantize(Decimal("0.01"))
                is_infinity = parse_bool(raw["is_infinity"])
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"line {line_no}: {exc}") from exc

            if not category:
                raise ValueError(f"line {line_no}: category is required")
            if not name:
                raise ValueError(f"line {line_no}: name is required")
            if not description:
                raise ValueError(f"line {line_no}: description is required")
            if price < 0:
                raise ValueError(f"line {line_no}: price must be >= 0")
            if not value:
                raise ValueError(f"line {line_no}: value is required")

            existing = product_defs.get(name)
            current = (category, description, price)
            if existing and existing != current:
                raise ValueError(
                    f"line {line_no}: product {name!r} has conflicting category, description, or price"
                )
            product_defs[name] = current

            rows.append(CatalogRow(category, name, description, price, value, is_infinity))

    return rows


async def seed(rows: list[CatalogRow]) -> None:
    from bot.database.models.main import register_models
    from bot.database.methods.create import create_category, create_item, add_values_to_item

    await register_models()

    categories = sorted({row.category for row in rows})
    products = {(row.category, row.name, row.description, row.price) for row in rows}

    for category in categories:
        await create_category(category)

    for category, name, description, price in sorted(products, key=lambda item: (item[0], item[1])):
        await create_item(name, description, price, category)

    inserted = 0
    skipped = 0
    for row in rows:
        if await add_values_to_item(row.name, row.value, row.is_infinity):
            inserted += 1
        else:
            skipped += 1

    print(f"Imported categories={len(categories)}, products={len(products)}, stock_inserted={inserted}, stock_skipped={skipped}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import digital products and deliverable stock values from CSV.")
    parser.add_argument("csv_path", type=Path, help="CSV with category,name,description,price,value,is_infinity columns.")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSV only; do not connect to the database.")
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"ERROR: CSV file not found: {args.csv_path}", file=sys.stderr)
        return 1

    try:
        rows = load_rows(args.csv_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    finite = sum(1 for row in rows if not row.is_infinity)
    infinite = len(rows) - finite
    print(f"Validated rows={len(rows)}, finite_stock={finite}, infinite_stock={infinite}.")

    if args.dry_run:
        return 0

    try:
        asyncio.run(seed(rows))
    except Exception as exc:
        print(f"ERROR: import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
