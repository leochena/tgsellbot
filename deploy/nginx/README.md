# TGSellBot Platform Nginx Entry

This directory contains the source-controlled nginx entrypoint for the Telegram Mini App.

Current production host:

```text
https://tg.1so.org/platform/app
```

The checked-in `tgsellbot-platform.conf` is the clean HTTP reverse-proxy base config. Certbot mutates the live copy under `/etc/nginx/sites-available/tgsellbot-platform` by adding HTTPS listeners, certificate paths, and HTTP-to-HTTPS redirects.

## Install Or Rebuild

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

sudo cp deploy/nginx/tgsellbot-platform.conf /etc/nginx/sites-available/tgsellbot-platform
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn /etc/nginx/sites-available/tgsellbot-platform /etc/nginx/sites-enabled/tgsellbot-platform
sudo nginx -t
sudo systemctl enable --now nginx

sudo certbot --nginx \
  -d tg.1so.org \
  -d 47-253-251-141.sslip.io \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  --redirect \
  --expand

sudo nginx -t
sudo systemctl reload nginx
```

## Production Checks

```bash
curl -fsS https://tg.1so.org/health
curl -fsS -o /tmp/platform_app.html https://tg.1so.org/platform/app
grep -q 'telegram-web-app.js' /tmp/platform_app.html
cd /opt/tgsellbot
/opt/tgsellbot/.venv/bin/python scripts/platform_ops.py platform-launch-check --smoke
certbot certificates -d tg.1so.org
```

The expected unauthenticated API behavior is a 401 response:

```bash
curl -sS -o /tmp/platform_api.json -w '%{http_code}' https://tg.1so.org/platform/api/channels/discover
grep -q 'telegram_init_data_invalid' /tmp/platform_api.json
```
