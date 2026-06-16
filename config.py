# config.py
# ============================================
# HABESHA BET - MULTIPLAYER BINGO BOT CONFIG
# Fill in the values marked "FILL IN" before running.
# ============================================

# ---------- TELEGRAM CORE ----------
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"          # FILL IN - from @BotFather
ADMIN_IDS = [123456789]                     # FILL IN - list of Telegram user IDs allowed to use /admin
BOT_USERNAME = "your_bot_username"          # FILL IN - without @, used for referral links
SUPPORT_USERNAME = "your_support_username"  # FILL IN - shown on "Contact Us" button
GROUP_LINK = "https://t.me/your_group"      # FILL IN - shown on "Join Group" button

# ---------- DATABASE ----------
DB_PATH = "habesha_bet.db"

# ---------- LANGUAGE ----------
DEFAULT_LANGUAGE = "am"   # "am" (Amharic) or "en" (English)

# ============================================
# BINGO ROOMS
# ============================================
# 4 permanent rooms, always available.
ROOM_FEES = [10, 20, 50, 100]   # ETB entry fee per card

CARD_POOL_SIZE = 200             # cards per room
MAX_CARDS_PER_PLAYER = 5         # max cards a single player can buy in one room

MIN_CARDS_TO_START = 2           # minimum cards sold before a game can start
COUNTDOWN_SECONDS = 60           # lobby countdown before game starts

CALL_DELAY_SECONDS = 2           # seconds between number calls
MAX_NUMBERS_CALLED = 75          # call all 75 balls maximum

# ---------- PRIZE SPLIT ----------
HOUSE_COMMISSION_PERCENT = 20    # house keeps 20% of the pool
# Remaining 80% is split equally among all winners of that round

# ---------- WIN TYPES ----------
# Only "line" (row/column/diagonal) and "corners" count as valid wins.
# Full House is intentionally NOT a separate win condition.
ENABLE_LINE_WIN = True
ENABLE_CORNERS_WIN = True
ENABLE_FULL_HOUSE_WIN = False

# ============================================
# DEPOSITS (TELEBIRR)
# ============================================
# Multiple Telebirr accounts can be configured; the active account
# rotates automatically after ROTATE_AFTER_DEPOSITS successful deposits.
# Accounts themselves are stored in the database (deposit_accounts table)
# so the admin can add/remove them live via /admin without redeploying.
ROTATE_AFTER_DEPOSITS = 20

MIN_DEPOSIT = 20      # ETB
DEPOSIT_QUICK_AMOUNTS = [50, 100, 200, 500, 1000]   # quick-select buttons; "Custom" always also offered

# ============================================
# WITHDRAWALS
# ============================================
MIN_WITHDRAWAL = 30   # ETB

# ============================================
# TRANSFERS (user to user)
# ============================================
MIN_TRANSFER = 10                # ETB
TRANSFER_COOLDOWN_SECONDS = 3600  # 1 hour between transfers per user

# ============================================
# REFERRAL & BONUS SETTINGS
# ============================================
REFERRAL_BONUS = 10          # ETB to referrer when their friend makes a first deposit
SIGNUP_BONUS = 5             # ETB to a new user who joined via a referral link
DAILY_BONUS_AMOUNT = 5       # ETB
DAILY_BONUS_COOLDOWN_HOURS = 24

# ============================================
# AUDIO (Amharic voice announcements)
# ============================================
# If a file named "{number}.ogg" exists in AUDIO_DIR (e.g. "12.ogg"),
# the bot sends it as a voice note when that number is called.
# If the file does not exist, the bot falls back to text-only.
# English audio is intentionally NOT supported - Amharic only.
AUDIO_DIR = "audio"
ENABLE_VOICE_ANNOUNCEMENTS = True

# ============================================
# HOUSE WALLET
# ============================================
# House commission is tracked in its own dedicated `house_wallet` table
# (balance = withdrawable now, total_earned = cumulative all-time).
# This ID is unused by the table design but kept reserved in case a
# pseudo-user representation is ever needed elsewhere.
HOUSE_ACCOUNT_ID = 0


# ============================================
# MASKING (for "last buyer" display, winner display, etc.)
# ============================================
# e.g. "@fUCijZmjgEq" -> "@fUC***" or "Abdi Mohammed" -> "@Ab8***"
MASK_VISIBLE_CHARS = 3

