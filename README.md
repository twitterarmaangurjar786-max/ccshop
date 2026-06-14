# 🏪 Telegram Redeem-Code Marketplace Bot

A **production-ready** Telegram marketplace for **redeem-code inventory** uploaded by sellers.
Built with **Aiogram 3**, **SQLAlchemy 2.0 (async)**, **PostgreSQL**, **Redis**, **Alembic**,
and **Docker Compose**.

> This is **not** an e-commerce store and **not** a product catalog.
> Sellers upload code lines; **categories are auto-generated from the first 6 digits** of every line.
> Inventory is always displayed as **Seller Name + Category + Price + Stock**.

---

## 👑 Roles (only three)

| Role   | Created by | Capabilities |
|--------|-----------|--------------|
| **Owner**  | `.env` `OWNER_IDS` | Full control: sellers, withdrawals, refunds, banners, broadcasts, coupons, tickets, settings, analytics, commissions |
| **Seller** | **Owner only** (`➕ Add Seller`) | Upload stock, manage inventory, view stats/earnings, withdraw, sales history |
| **Buyer**  | Automatic on `/start` | Search, browse sellers, filter, buy, top-up, pre-order, export, refund, support |

There is **no Admin role**, **no admin panel**, **no "Become Seller" button**, and **no seller-application system**.
**Only the Owner creates sellers** (by Telegram ID + Marketplace Name).

---

## 🧩 Key concepts

### Auto categories
Every uploaded line looks like:

```
12345678902772|298/3883|abc
```

The **first 6 digits** (`123456`) **are** the category. No manual categories, no names, no products.

### Upload pipeline
1. Seller sends `.txt` / `.csv`.
2. System counts **total / duplicate / valid** lines (dedupe **inside file** and **inside DB** via SHA-256 hash).
3. System extracts the first 6 digits and **auto-creates categories**.
4. Seller enters **price per line**, confirms, and inventory is saved.

### Purchase pipeline
1. Buyer searches a 6-digit category or browses sellers.
2. Picks a seller offer → enters quantity.
3. Lines are **reserved for 5 minutes** (Redis + DB locks) so no one else can buy them.
4. On pay: lines are delivered (message **and** TXT file), marked sold, stock reduced,
   transaction created, **seller credited 90% / owner 10%** (configurable).

---

## 🗂 Project structure

```
ccshop/
├── docker-compose.yml          # postgres + redis + bot
├── Dockerfile
├── alembic.ini
├── requirements.txt
├── .env.example
├── scripts/entrypoint.sh       # waits for DB, runs migrations, starts bot
├── alembic/                    # migrations (0001_initial = full schema)
└── app/
    ├── main.py                 # entrypoint (long-polling)
    ├── bot.py                  # dispatcher, middlewares, scheduler, lifecycle
    ├── config.py               # pydantic-settings (env)
    ├── database.py             # async engine + session factory
    ├── redis_client.py         # redis connection
    ├── logger.py               # structured logging
    ├── constants.py            # enums + redis keys
    ├── keyboards.py            # all reply/inline keyboards
    ├── states.py               # FSM state groups
    ├── models/                 # SQLAlchemy 2.0 models (all tables)
    ├── repositories/           # data-access layer
    ├── services/               # business logic (upload, purchase, wallet, crypto…)
    ├── middlewares/            # db session, auth/role, throttling, logging
    └── handlers/               # routers: common, owner, seller, buyer
```

### Database tables
`users`, `wallets`, `sellers`, `seller_inventory`, `inventory_lines`, `orders`, `purchases`,
`transactions`, `deposits`, `withdrawals`, `coupons`, `coupon_redemptions`, `referrals`,
`tickets`, `ticket_messages`, `refunds`, `pre_orders`, `broadcasts`, `banners`,
`audit_logs`, `settings`.

---

## ✨ Features

- **Owner dashboard** — users, sellers, inventory, stock, sales, deposits, withdrawals, revenue, commission, open tickets.
- **Seller management** — add / remove / suspend / unsuspend / list.
- **Upload** — txt/csv scan, duplicate detection (file + DB), auto categories, price entry, confirm.
- **Seller inventory** — category / stock / price / sold / remaining; edit price before first sale; delete unsold.
- **Search** — type a 6-digit code → all sellers for that category (name + price + stock).
- **Filters** — category / seller / price range / availability; saved per-user (Redis) and shown on Home.
- **Purchase + 5-min reservation** with concurrency-safe locks.
- **Delivery** — Telegram message **and** downloadable TXT.
- **Commission** — default 90/10, runtime-configurable, per-seller override.
- **Crypto** — USDT-TRC20 / TRX deposits (address generation + polling) and withdrawals (owner approval).
- **Coupons** — percentage / fixed, expiry, usage limit.
- **Pre-orders** — register interest for low/zero-stock categories; auto-notify on new upload.
- **Referrals** — link, reward, statistics.
- **Support tickets**, **refunds**, editable **Rules / Contacts / Refund** pages.
- **Banners** — image / video / GIF, rotating, button links, enable/disable.
- **Broadcasts** — text/photo/video/document to All / Buyers / Sellers with delivered/failed/blocked counts.
- **Security** — rate limiting + anti-spam (Redis), audit logs, reservation locks, duplicate prevention,
  input validation, error logging, Redis caching.

---

## 🚀 Quick start (Docker)

```bash
cp .env.example .env
#  → edit BOT_TOKEN and OWNER_IDS

docker compose up -d --build
docker compose logs -f bot
```

Migrations run automatically on container start (`scripts/entrypoint.sh`).

### Local (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set POSTGRES_HOST=localhost, REDIS_HOST=localhost
alembic upgrade head
python -m app.main
```

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for full Ubuntu VPS instructions, backups, and updates.

---

## ⚙️ Configuration (`.env`)

| Var | Description |
|-----|-------------|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `OWNER_IDS` | Comma-separated owner Telegram IDs |
| `POSTGRES_*` | Database connection |
| `REDIS_*` | Redis connection |
| `DEFAULT_SELLER_PERCENT` / `DEFAULT_OWNER_PERCENT` | Commission split |
| `RESERVATION_MINUTES` | Inventory hold time (default 5) |
| `TRON_API_KEY`, `USDT_TRC20_CONTRACT`, `DEPOSIT_MASTER_WALLET` | Crypto |
| `RATE_LIMIT_PER_SECOND` | Anti-spam throttle |

---

## 🔐 Notes
- Internal batch / line IDs are **never** shown to buyers.
- All financial mutations go through the wallet service with transaction records and audit logs.
- The deposit poller is safe to run without crypto keys (it simply no-ops).
