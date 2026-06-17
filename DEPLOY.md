# DEPLOY.md — Habesha Bet: One-Host Deployment to Render

## 1. Build the frontend locally first

```
cd miniapp
npm install
npm run build
```

This creates `miniapp/dist/`. Commit it (or let Render build it — see step 4 alt).

## 2. Push everything to your private GitHub repo

Repo root must contain: `bot.py`, `database.py`, `bingo.py`, `sms_parser.py`,
`locales.py`, `config.py`, `game_state.py`, `telegram_auth.py`,
`api_handlers.py`, `api_server.py`, `requirements.txt`, and the `miniapp/`
folder (with `dist/` built).

## 3. Create the Render service

- New → Web Service → connect your repo
- **Build Command:**
  ```
  pip install -r requirements.txt && cd miniapp && npm install && npm run build
  ```
- **Start Command:**
  ```
  python bot.py
  ```
- **Instance Type:** Free
- Render auto-sets `PORT` — `bot.py` already reads it (`os.environ.get("PORT", ...)`)

## 4. Set environment variables on Render

Don't commit real secrets to `config.py`. Instead edit `config.py` to read
from env vars, OR (simplest) just edit `config.py` directly with real
values before pushing to a **private** repo. Minimum required:

```
BOT_TOKEN = "<from @BotFather>"
ADMIN_IDS = [<your numeric Telegram id>]
BOT_USERNAME = "<your_bot_username>"
MINI_APP_URL = "https://<your-render-service>.onrender.com"
```

`MINI_APP_URL` must be set to your Render URL — this is what makes the
"Open Habesha Bet" button appear and is also the value `bot.py` uses to
register Telegram's menu button on startup.

## 5. Deploy

Push to GitHub → Render auto-deploys. Watch logs for:
```
API server starting on 0.0.0.0:<port> ...
Habesha Bet bot starting...
```

## 6. Verify

- Visit `https://<your-service>.onrender.com/health` → `{"status":"ok"}`
- Open your bot in Telegram, send `/start`
- Tap the menu button (bottom-left, next to the message box) or the
  "Open Habesha Bet" inline button → Mini App should load

## 7. Free-tier note

Render free web services sleep after 15 min idle and cold-start on the
next request (10–30s delay). Acceptable for testing; for production
either upgrade to a paid instance or use a cron ping to `/health` every
10 min to keep it warm.

## Troubleshooting

- **Mini App shows blank screen:** check browser console via Telegram
  Desktop (right-click → Inspect) — usually a missing `dist/` build.
- **401 errors on every API call:** `BOT_TOKEN` in `config.py` doesn't
  match the bot the Mini App was opened from — `initData` is signed
  per-bot.
- **Menu button doesn't appear:** `MINI_APP_URL` wasn't set before
  `bot.py` started — restart the service after setting it.
