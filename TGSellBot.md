# TGSellBot

TGSellBot is a Telegram 24/7 auto-sales bot for legal digital goods, JSON-file delivery, points redemption, group invite rewards, lotteries, and web-based shop operations.

Use it for legal goods only, such as license keys, invite codes, membership codes, account entitlements, JSON credentials, or other deliverable values that can be sent automatically after purchase.

## Repository State

- Repository: `https://github.com/leochena/tgsellbot`
- Main operations guide: `docs/OPERATIONS.md`
- Chinese README: `README.zh-CN.md`
- Current screenshots: `assets/admin-login-zh.png`, `assets/product-operations-zh.png`, `assets/json-stock-form-zh.png`
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

Then fill real `.env` credentials, start PostgreSQL, run migrations, import real stock, and launch `run.py` or `run_admin.py`.

## Language Support

The default bot language comes from `BOT_LOCALE`, and each user can override it from the bot language menu. The current built-in bot locales are `ru`, `en`, and `zh`.

The web admin UI supports Chinese and English, plus 12/14/16/18 pt font-size switching.

## Engagement Modules

Daily check-in, group invite rewards, points redemption, and lottery are integrated into the same bot. Check-in credits points, not cash balance, and can issue tickets for the active lottery. Invite rewards are credited only after the invited user joins through a personal invite link and completes check-in.

Admins manage product prize-pool settings, lottery events, bot settings, and invite reward tiers from the web admin.
