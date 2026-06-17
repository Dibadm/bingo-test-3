"""
config.py — All settings, constants, and tunable parameters.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot credentials ────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("HABESHA_BOT_TOKEN", "")
ADMIN_ID: int = int(os.getenv("HABESHA_ADMIN_ID", "0"))

# ── Rooms ──────────────────────────────────────────────────────────────────────
ROOM_FEES: list[int] = [10, 20, 50, 100]        # ETB entry fees

# ── Card pool ─────────────────────────────────────────────────────────────────
TOTAL_CARDS: int = 200                           # cards available per game
MAX_CARDS_PER_PLAYER: int = 5                    # max a single player may buy

# ── Timing ─────────────────────────────────────────────────────────────────────
COUNTDOWN_SECONDS: int = 60                      # lobby countdown before start
CALL_INTERVAL_SECONDS: float = 2.0              # pause between number calls
MIN_CARDS_TO_START: int = 2                      # cards sold before countdown

# ── Finance ────────────────────────────────────────────────────────────────────
HOUSE_COMMISSION: float = 0.20                   # 20 % of total pot
MIN_DEPOSIT: int = 20                            # ETB
MIN_WITHDRAWAL: int = 30                         # ETB
MIN_TRANSFER: int = 10                           # ETB
TRANSFER_COOLDOWN_SECONDS: int = 3_600           # 1 hour

# ── Deposit account rotation ───────────────────────────────────────────────────
DEPOSITS_PER_ROTATION: int = 20                  # rotate after N successful deposits

# ── Telebirr SMS verification ─────────────────────────────────────────────────
# Accepted recipient name fragments (lowercase, partial match OK)
ACCEPTED_RECIPIENT_NAMES: list[str] = ["habesha bet", "habeshabet"]
# Last 4 digits of the accepted Telebirr phone numbers
ACCEPTED_PHONE_LAST4: list[str] = ["6789", "1234"]   # update to real digits

# ── Referral ───────────────────────────────────────────────────────────────────
REFERRAL_BONUS: float = 5.0                      # ETB reward for both parties

# ── Default Telebirr deposit accounts (admin can add more via /admin) ──────────
DEFAULT_TELEBIRR_ACCOUNTS: list[dict] = [
    {"phone": "0912346789", "name": "Habesha Bet"},
]

# ── Database ───────────────────────────────────────────────────────────────────
DB_PATH: str = os.path.join(os.path.dirname(__file__), "habesha_bingo.db")

# ── Audio ──────────────────────────────────────────────────────────────────────
AUDIO_DIR: str = os.path.join(os.path.dirname(__file__), "audio")
# Place files named 1.ogg … 75.ogg inside the audio/ folder.

# ── Community ──────────────────────────────────────────────────────────────────
GROUP_LINK: str = os.getenv("HABESHA_GROUP_LINK", "https://t.me/your_group")
CONTACT_USERNAME: str = os.getenv("HABESHA_CONTACT", "@your_support")
BOT_USERNAME: str = os.getenv("HABESHA_BOT_USERNAME", "your_bot")

# ── UI helpers ─────────────────────────────────────────────────────────────────
CARDS_PER_PAGE: int = 50          # cards shown per page in card-selection grid
