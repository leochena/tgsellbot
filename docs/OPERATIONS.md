# Telegram 24/7 Auto-Sales Bot Operations

This project is a deployable Telegram digital-goods shop bot. It sells products inside Telegram, accepts balance top-ups through enabled payment providers, and automatically delivers the stored item value after a successful purchase.

## What Is Done

- Source base: `interlumpen/Telegram-shop`, MIT licensed.
- Bot framework: Python, Aiogram 3.
- Database: PostgreSQL with Alembic migrations.
- Optional cache/session storage: Redis.
- Admin UI: SQLAdmin at `/admin`.
- Payment options already supported by the codebase:
  - CryptoPay.
  - Telegram Stars.
  - Stripe/card payments through a Telegram Payments provider token.
- Digital delivery model:
  - Product metadata lives in `goods`.
  - Deliverable stock/card/license/account values live in `item_values`.
  - Purchase records live in `bought_goods`.
  - A finite stock value is removed from `item_values` after sale.
  - An infinite value remains reusable after sale.

## Credentials You Must Provide

Do not commit real secrets.

- `TOKEN`: Telegram bot token from BotFather.
- `OWNER_ID`: your Telegram numeric user ID.
- `POSTGRES_PASSWORD`: strong database password.
- `ADMIN_USERNAME`: admin web login.
- `ADMIN_PASSWORD`: strong admin web password.
- `SECRET_KEY`: random web session secret.
- At least one payment method:
  - `CRYPTO_PAY_TOKEN`, or
  - `STARS_PER_VALUE` greater than `0`, or
  - `TELEGRAM_PROVIDER_TOKEN`.

`TELEGRAM_PROVIDER_TOKEN` is the Telegram Payments provider token used for Stripe/card checkout. Connect the payment provider in BotFather and paste the resulting provider token into `.env`; do not put a Stripe secret key directly into this bot unless you later add a separate Stripe Checkout webhook flow.

For production, also set:

- `BOT_LOCALE=en` or `ru` as the default language for users who have not chosen their own language.
- `PAY_CURRENCY=USD`, `EUR`, `RUB`, or another Telegram-supported 3-letter provider currency where relevant.
- `BALANCE_CURRENCY=UStars` or another internal balance label shown to users. This is not a real fiat currency.
- `REDIS_ENABLED=1` with Redis available, or `0` for simpler low-traffic polling mode.
- `CHECKIN_POINTS_REWARD`: points credited for each daily check-in. `CHECKIN_REWARD_AMOUNT` is still accepted as a legacy fallback.
- `CHECKIN_TICKETS_PER_DAY`: lottery tickets awarded to the current active lottery on check-in.

## Local Windows Bring-Up

Use this for configuration and dry-run checks. Production should run on a VPS.

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install --upgrade pip
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv312\Scripts\python.exe scripts\check_config.py
```

Edit `.env` until `scripts\check_config.py` reports no blocking errors.

If you have a local PostgreSQL server:

```powershell
.\.venv312\Scripts\alembic.exe upgrade head
.\.venv312\Scripts\python.exe scripts\seed_catalog.py examples\products.sample.csv
.\.venv312\Scripts\python.exe run.py
```

The admin panel listens on `http://localhost:9090/admin`.

You can also use the Windows helper after `.env` is filled and PostgreSQL is running:

```powershell
.\scripts\start_windows.ps1
```

## VPS Production Deployment

Recommended: Ubuntu VPS with Docker and Docker Compose.

```bash
git clone <your-repo-url> tgsellbot
cd tgsellbot
cp .env.example .env
nano .env
docker compose --profile redis up -d --build
docker compose logs -f bot
```

If you do not want Redis at first:

```bash
sed -i 's/^REDIS_ENABLED=.*/REDIS_ENABLED=0/' .env
docker compose up -d --build
```

Keep the admin panel bound to localhost unless you put it behind a trusted tunnel or reverse proxy with access control.

If you deploy without Docker, use `deploy/systemd/tgsellbot.service` as the systemd template. Adjust `/opt/tgsellbot`, user/group, PostgreSQL, and Redis service names to match the VPS.

## Importing Products And Stock

Use CSV import for initial catalog and future restocks:

```powershell
.\.venv312\Scripts\python.exe scripts\seed_catalog.py examples\products.sample.csv --dry-run
.\.venv312\Scripts\python.exe scripts\seed_catalog.py path\to\stock.csv
```

CSV columns:

- `category`: product category shown in shop navigation.
- `name`: product name.
- `description`: product description.
- `price`: numeric internal balance price shown in `BALANCE_CURRENCY`.
- `value`: delivered value, such as a license key, invite code, account credential, or download code.
- `is_infinity`: `true` if the same value can be delivered unlimited times, otherwise `false`.

Never commit real stock CSV files. `.gitignore` ignores `stock*.csv` and `products*.csv`; keep real inventory outside git when possible.

## Go-Live Checklist

1. Create a Telegram bot in BotFather and set `TOKEN`.
2. Get your Telegram numeric ID and set `OWNER_ID`.
3. Choose payment method and set the required token/rate.
   - Use Telegram Stars for digital goods sold inside Telegram.
   - Use `TELEGRAM_PROVIDER_TOKEN` for Stripe/card payments when selling physical goods or services supported by Telegram Payments.
4. Set strong `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, and `SECRET_KEY`.
5. Run `scripts/check_config.py`.
6. Start PostgreSQL/Redis and run Alembic migrations.
7. Import product stock with `scripts/seed_catalog.py`.
8. Start the bot.
9. Send `/start` to the bot from the owner account.
10. Make one low-value test purchase and confirm the delivered value is correct.
11. Check admin panel, `/health`, logs, and purchase export.

## Per-User Language

The bot has a per-user language setting. Users can open Profile and press Language to choose one of the supported locales. Their choice is stored in `users.locale` and overrides the global `BOT_LOCALE` for their own messages and callbacks.

Current built-in locales:

- `ru`
- `en`

For existing deployments, run migrations before restarting the updated bot:

```powershell
.\.venv312\Scripts\alembic.exe upgrade head
```

or on Docker:

```bash
docker compose run --rm bot alembic upgrade head
```

## Check-In And Lottery

The bot includes linked engagement modules:

- Users press Daily check-in from the main menu.
- A successful daily check-in credits `CHECKIN_POINTS_REWARD` to the user's points balance.
- If an active lottery exists, the same check-in grants `CHECKIN_TICKETS_PER_DAY` lottery entries.
- Products can set `points_price`; a value greater than `0` enables one-item points redemption for that product.
- Users can open Lottery from the main menu to see the active event, total tickets, participant count, their own tickets, and check-in status.
- Admins with promo-management permission can open Admin panel -> Lotteries to create a lottery, draw a winner, or close the current event.

Operational notes:

- A user can check in only once per UTC day.
- Creating a new lottery automatically closes any previously active lottery.
- Lottery winners are drawn randomly from individual entries, so more tickets increase the winning probability.
- Drawing a winner changes the event status to `drawn`; closing changes it to `closed`.
- Check-in rewards are recorded as points, not cash balance. They appear in `users.points_balance` and do not create cash-balance operation history.
- Group invite rewards are credited only after the invited user joins through a personal invite link and completes check-in.
- `bot_settings.group_invite_reward_tiers` controls tiered invite rewards. Use `1=1,10=2,30=3`: the left side is the inviter's cumulative successful invite count, the right side is the points for this invite. Empty value falls back to fixed `GROUP_INVITE_REWARD_POINTS`.

## 24/7 Running Notes

- Use Docker `restart: unless-stopped` on VPS.
- Keep polling mode for simple deployments. Use webhook mode only when you have a stable HTTPS public URL.
- Back up PostgreSQL regularly. It contains users, balances, payments, purchases, and unsold inventory.
- Treat `item_values.value` as sensitive because it contains deliverable goods.
- Rotate payment/admin credentials if they are exposed.
- Monitor logs and `/health` after restocks and payment-provider changes.
