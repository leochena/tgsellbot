# TGSellBot

TGSellBot is a Telegram 24/7 auto-sales bot based on `interlumpen/Telegram-shop`.

Use it for legal digital goods only, such as license keys, invite codes, membership codes, account entitlements, or other deliverable text values that can be sent automatically after purchase.

## Current Local State

- Repository path: `D:\tgsellbot`
- Upstream source: `https://github.com/interlumpen/Telegram-shop.git`
- Main operations guide: `docs/OPERATIONS.md`
- Config checker: `scripts/check_config.py`
- Catalog importer: `scripts/seed_catalog.py`
- Windows runner: `scripts/start_windows.ps1`
- systemd template: `deploy/systemd/tgsellbot.service`
- Sample catalog: `examples/products.sample.csv`

## Fast Path

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv312\Scripts\python.exe scripts\check_config.py
.\.venv312\Scripts\python.exe scripts\seed_catalog.py examples\products.sample.csv --dry-run
```

Then fill real `.env` credentials, start PostgreSQL, run migrations, import real stock, and launch `run.py`.

## Language Support

The default interface language comes from `BOT_LOCALE`, and each user can override it from Profile -> Language. The current built-in locales are `ru` and `en`.

## Engagement Modules

Daily check-in and lottery are integrated into the same bot. Check-in credits user balance and can issue tickets for the active lottery. Admins manage lotteries from Admin panel -> Lotteries.
