# 🎯 Habesha Bet Bingo Bot

A full multiplayer Bingo platform for Telegram with real-money ETB rooms, Telebirr SMS deposits, live prize pools, and a React WebApp UI.

## Features

- 🎮 **4 Permanent Rooms** — 10 / 20 / 50 / 100 ETB entry fees
- 🃏 **200 cards per game** — up to 5 per player
- ⏱ **60-second countdown** starts when ≥ 2 cards sold
- 🔔 **Auto-call** every 2 seconds (numbers 1–75)
- 🏆 **80% prize pool** split among all winners (Line + Corners wins)
- 💰 **Telebirr SMS deposits** with account rotation every 20 deposits
- 💸 **Admin withdrawal approval** panel
- 🌐 **Bilingual** — English & Amharic (🇪🇹)
- 📱 **React Telegram Mini App** for card selection & game board

## Project Structure

```
habesha-bingo/
├── bot.py          ← Main bot + game engine (asyncio)
├── database.py     ← SQLite CRUD with aiosqlite
├── bingo.py        ← Card generation & win detection
├── locales.py      ← EN/AM string dictionary
├── sms_parser.py   ← Telebirr SMS parser
├── config.py       ← All settings (env-driven)
├── requirements.txt
├── webapp/         ← React Telegram Mini App (Vite + TypeScript)
│   ├── src/pages/CardSelection.tsx
│   ├── src/pages/GameBoard.tsx
│   └── ...
├── Procfile        ← Railway / Heroku deploy
├── render.yaml     ← Render deploy
└── railway.toml    ← Railway deploy config
```

## Deployment (Railway — recommended)

1. Fork this repo or push to your GitHub
2. Connect repo to [Railway](https://railway.app)
3. Set environment variables in Railway dashboard:
   - `HABESHA_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `HABESHA_ADMIN_ID` — your Telegram numeric ID
   - `HABESHA_BOT_USERNAME` — your bot's username (without @)
   - `HABESHA_GROUP_LINK` — your Telegram group link
   - `HABESHA_CONTACT` — support username

## WebApp Deployment (GitHub Pages)

The React webapp auto-deploys to GitHub Pages on every push to `main` via GitHub Actions.

1. Go to **Settings → Pages → Source → GitHub Actions**
2. Add repo variable `VITE_API_URL` = your Railway bot URL (e.g. `https://your-bot.up.railway.app`)
3. Push to main — webapp builds and deploys automatically

The bot sends the WebApp URL as `https://<your-github>.github.io/bingo-test-3/card-selection?room=10`

## Local Development

```bash
# Install Python deps
pip install -r requirements.txt

# Set env vars
export HABESHA_BOT_TOKEN="your_token"
export HABESHA_ADMIN_ID="your_telegram_id"

# Run bot
python bot.py
```

## Telebirr SMS Configuration

Edit `config.py`:
- `ACCEPTED_RECIPIENT_NAMES` — name fragments shown in Telebirr confirmation SMS
- `ACCEPTED_PHONE_LAST4` — last 4 digits of your Telebirr receiving number(s)

Add deposit accounts via admin panel: `/admin → 🏦 Accounts`

## Win Types

| Type | Description |
|------|-------------|
| Line | Any complete row, column, or diagonal |
| Corners | All 4 corner squares marked |
| ~~Full House~~ | ~~All 25 squares~~ — **Disabled** |

Multiple winners on the same number call split the 80% pot equally.
