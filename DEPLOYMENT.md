# 🚀 Deployment Guide — Ubuntu VPS

Production deployment of the Telegram Marketplace Bot using Docker Compose.

---

## 1. Prerequisites

- Ubuntu 22.04 / 24.04 VPS (1 vCPU / 1–2 GB RAM minimum)
- A domain is **not** required (the bot uses long-polling)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram ID (get it from [@userinfobot](https://t.me/userinfobot))

---

## 2. Install Docker

```bash
sudo apt-get update && sudo apt-get upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version
```

---

## 3. Get the code

```bash
# via git
git clone <your-repo-url> marketplace && cd marketplace

# …or upload the project folder with scp/rsync
# rsync -avz ./ccshop/ user@SERVER_IP:/home/user/marketplace/
```

---

## 4. Configure environment

```bash
cp .env.example .env
nano .env
```

Set at minimum:

```env
BOT_TOKEN=123456789:AA...your-token
OWNER_IDS=YOUR_TELEGRAM_ID            # comma-separated for multiple owners
POSTGRES_PASSWORD=use_a_strong_password
```

Inside Docker, keep `POSTGRES_HOST=postgres` and `REDIS_HOST=redis` (the service names).

---

## 5. Launch

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f bot          # watch startup + migrations
```

The `bot` container automatically:
1. waits for PostgreSQL to be healthy,
2. runs `alembic upgrade head`,
3. starts long-polling.

Open Telegram, send `/start` to your bot from an **owner** account → you'll get the Owner menu.

---

## 6. Create your first seller

In Telegram (as Owner):

```
👤 Sellers → ➕ Add Seller
→ enter Telegram ID:  123456789
→ enter Seller Name:  DragonStore
```

The seller immediately receives seller permissions and the seller menu.

---

## 7. Common operations

```bash
# View logs
docker compose logs -f bot

# Restart the bot only
docker compose restart bot

# Stop / start everything
docker compose down
docker compose up -d

# Rebuild after code changes
git pull
docker compose up -d --build

# Open a shell in the bot container
docker compose exec bot bash

# Run a migration manually
docker compose exec bot alembic upgrade head

# Create a new migration after model changes
docker compose exec bot alembic revision --autogenerate -m "describe change"
```

---

## 8. Database backups

Manual backup:

```bash
docker compose exec -T postgres pg_dump -U marketplace marketplace \
  | gzip > backups/marketplace_$(date +%F_%H%M).sql.gz
```

Automated daily backup (cron). Create `/home/$USER/marketplace/backup.sh`:

```bash
#!/usr/bin/env bash
cd /home/$USER/marketplace
mkdir -p backups
docker compose exec -T postgres pg_dump -U marketplace marketplace \
  | gzip > backups/marketplace_$(date +%F_%H%M).sql.gz
# keep last 14 backups
ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --
```

Then:

```bash
chmod +x backup.sh
crontab -e
# add: run every day at 03:00
0 3 * * * /home/$USER/marketplace/backup.sh >> /home/$USER/marketplace/backups/cron.log 2>&1
```

Restore:

```bash
gunzip -c backups/marketplace_YYYY-MM-DD_HHMM.sql.gz \
  | docker compose exec -T postgres psql -U marketplace -d marketplace
```

---

## 9. Updating the bot

```bash
cd marketplace
git pull
docker compose up -d --build bot
docker compose logs -f bot
```

Migrations apply automatically on restart.

---

## 10. Hardening (recommended)

- **Firewall**: only allow SSH (and close 5432/6379 to the public — they're only used internally by Docker).
  ```bash
  sudo ufw allow OpenSSH
  sudo ufw enable
  ```
  > Note: the compose file maps `5432`/`6379` to the host for convenience.
  > For production, remove those `ports:` mappings so Postgres/Redis stay private.
- Use a strong `POSTGRES_PASSWORD` and set a `REDIS_PASSWORD`.
- Keep `.env` out of version control (already in `.gitignore`).
- Enable automatic security updates: `sudo apt-get install unattended-upgrades`.
- Monitor with `docker compose logs` or ship logs from `./logs/` to your aggregator.

---

## 11. Health checks & troubleshooting

| Symptom | Check |
|---------|-------|
| Bot not responding | `docker compose logs bot` — token valid? owner ID correct? |
| `connection refused` to DB | `docker compose ps` — is `postgres` healthy? |
| Migrations fail | `docker compose exec bot alembic upgrade head` and read the error |
| Deposits not detected | Set `TRON_API_KEY` / `DEPOSIT_MASTER_WALLET`; poller no-ops without them |
| Duplicate uploads ignored | Expected — dedupe is by SHA-256 of each line (file + DB) |

---

## 12. Scaling notes

- The bot is **stateless** apart from PostgreSQL + Redis; you can move those to managed services.
- Reservation locks and rate limiting use Redis, so a single bot instance is recommended with polling.
- For very high throughput, switch to webhooks behind Nginx and run multiple workers — the code is
  structured (services/repositories) to support that with minimal changes.
```
