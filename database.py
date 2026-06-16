# database.py
# ============================================
# HABESHA BET - DATABASE LAYER
# SQLite, row_factory = sqlite3.Row throughout.
#
# Tables:
#   users            - accounts, balances, phone, language, referrals
#   transactions     - full ledger of every balance change
#   withdrawals      - pending/approved/rejected withdrawal requests
#   deposit_accounts - rotating Telebirr accounts for deposits
#   games            - one row per bingo round (per room)
#   game_players     - players in a game + their auto-win toggle
#   game_cards       - cards sold in a game (ownership + manual marks)
#   game_numbers     - the sequence of called numbers per game
#
# Concurrency notes:
#   - Card purchases use a UNIQUE index on (game_id, card_index) so two
#     players can NEVER buy the same card - the second INSERT fails with
#     IntegrityError and the whole purchase is rolled back.
#   - Transfers use a conditional UPDATE (WHERE balance >= amount) so a
#     user can never go negative even under concurrent requests.
#   - Deposit reference numbers are UNIQUE so the same Telebirr SMS can
#     never be credited twice.
# ============================================

import sqlite3
import json
from datetime import datetime, timedelta

import config


def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables and indexes if they don't exist. Safe to call every startup."""
    conn = get_connection()
    cur = conn.cursor()
    _init_tables(cur)
    conn.commit()
    conn.close()
    init_house_wallet()


def _init_tables(cur):

    # ---------------- USERS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            phone TEXT,
            balance REAL NOT NULL DEFAULT 0,
            language TEXT NOT NULL DEFAULT 'am',
            referred_by INTEGER,
            referral_bonus_given INTEGER NOT NULL DEFAULT 0,
            last_bonus_claim TEXT,
            last_transfer_time TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # ---------------- TRANSACTIONS (full ledger) ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            -- types: deposit, withdraw, withdraw_refund, transfer_in, transfer_out,
            --        bingo_bet, bingo_win, bingo_refund,
            --        referral_bonus, signup_bonus, daily_bonus,
            --        house_commission
            amount REAL NOT NULL,
            reference TEXT,
            status TEXT NOT NULL,   -- completed, pending, rejected
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_reference
        ON transactions(reference)
        WHERE reference IS NOT NULL
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_type ON transactions(type)")

    # ---------------- WITHDRAWALS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            phone TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)

    # ---------------- DEPOSIT ACCOUNTS (rotating Telebirr numbers) ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposit_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            recipient_name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0,
            deposit_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # ---------------- GAMES ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_fee REAL NOT NULL,
            state TEXT NOT NULL DEFAULT 'waiting',  -- waiting, running, finished
            pool REAL NOT NULL DEFAULT 0,
            house_cut REAL,
            winner_ids TEXT,           -- JSON list of user_ids, set when finished
            per_winner_amount REAL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_games_room_state ON games(room_fee, state)")

    # ---------------- GAME PLAYERS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            cards_count INTEGER NOT NULL DEFAULT 0,
            auto_win INTEGER NOT NULL DEFAULT 0,
            chat_id INTEGER,
            message_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(game_id, user_id)
        )
    """)

    # ---------------- GAME CARDS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            card_index INTEGER NOT NULL,   -- 0-199, position in the 200-card pool
            owner_id INTEGER NOT NULL,
            marked_numbers TEXT NOT NULL DEFAULT '[]',  -- JSON list, manual tap-to-highlight
            created_at TEXT NOT NULL,
            UNIQUE(game_id, card_index)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_game ON game_cards(game_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cards_owner ON game_cards(game_id, owner_id)")

    # ---------------- GAME NUMBERS (call sequence) ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            call_order INTEGER NOT NULL,   -- 1, 2, 3 ... up to 75
            number INTEGER NOT NULL,       -- the ball number 1-75
            called_at TEXT NOT NULL,
            UNIQUE(game_id, call_order),
            UNIQUE(game_id, number)
        )
    """)

    # ---- Migration for older DBs (safe to run every time) ----
    for column, col_def in [
        ("phone", "TEXT"),
        ("language", "TEXT NOT NULL DEFAULT 'am'"),
        ("referred_by", "INTEGER"),
        ("referral_bonus_given", "INTEGER NOT NULL DEFAULT 0"),
        ("last_bonus_claim", "TEXT"),
        ("last_transfer_time", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {column} {col_def}")
        except sqlite3.OperationalError:
            pass


# =====================================================================
# USERS
# =====================================================================

def find_user_by_username(username: str) -> sqlite3.Row:
    """Case-insensitive lookup by username (without leading @), used for
    the transfer flow where the sender types the recipient's @handle.
    Returns the most recently created matching user if somehow more than
    one row shares a username (e.g. stale data from a username change)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?) ORDER BY created_at DESC LIMIT 1",
        (username,)
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_or_create_user(user_id: int, username: str, referred_by: int = None) -> sqlite3.Row:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()

    if user is None:
        cur.execute(
            "INSERT INTO users (user_id, username, balance, language, referred_by, created_at) "
            "VALUES (?, ?, 0, ?, ?, ?)",
            (user_id, username, config.DEFAULT_LANGUAGE, referred_by, datetime.utcnow().isoformat())
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()

    conn.close()
    return user


def get_user(user_id: int) -> sqlite3.Row:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user


def get_balance(user_id: int) -> float:
    user = get_user(user_id)
    return user["balance"] if user else 0.0


def adjust_balance(user_id: int, amount: float) -> float:
    """Add (or subtract, if negative) to a user's balance. Returns new balance."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    new_balance = cur.fetchone()["balance"]
    conn.close()
    return new_balance


def set_user_phone(user_id: int, phone: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
    conn.commit()
    conn.close()


def set_user_language(user_id: int, lang: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()


def get_all_user_ids() -> list:
    """For broadcast - returns all registered user_ids."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def count_users() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users")
    row = cur.fetchone()
    conn.close()
    return row["c"]


# =====================================================================
# TRANSACTIONS / LEDGER
# =====================================================================

def record_transaction(user_id: int, tx_type: str, amount: float, reference: str = None, status: str = "completed"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (user_id, type, amount, reference, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, tx_type, amount, reference, status, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def reference_already_used(reference: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM transactions WHERE reference = ?", (reference,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_user_transactions(user_id: int, limit: int = 10) -> list:
    """Most recent transactions for this user, newest first - used for
    the '/Transactions' menu screen."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def count_deposits(user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) as c FROM transactions WHERE user_id = ? AND type = 'deposit' AND status = 'completed'",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row["c"] if row else 0


def get_total_collected() -> float:
    """Sum of all completed deposits - for admin dashboard."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM transactions WHERE type='deposit' AND status='completed'")
    row = cur.fetchone()
    conn.close()
    return row["total"]


def get_net_profit() -> float:
    """Sum of all house_commission transactions - for admin dashboard."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM transactions WHERE type='house_commission'")
    row = cur.fetchone()
    conn.close()
    return row["total"]


def get_peak_hours() -> list:
    """Returns [(hour_0_23, count), ...] based on bingo_bet transactions (UTC hour)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour, COUNT(*) as count
        FROM transactions
        WHERE type = 'bingo_bet'
        GROUP BY hour
        ORDER BY hour
    """)
    rows = cur.fetchall()
    conn.close()
    return [(r["hour"], r["count"]) for r in rows]


# =====================================================================
# REFERRALS & BONUSES
# =====================================================================

def count_referrals(user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users WHERE referred_by = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row["c"] if row else 0


def mark_referral_bonus_given(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET referral_bonus_given = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def can_claim_daily_bonus(user_id: int):
    """Returns (can_claim: bool, hours_remaining: float)."""
    user = get_user(user_id)
    if user is None or user["last_bonus_claim"] is None:
        return True, 0.0

    last_claim = datetime.fromisoformat(user["last_bonus_claim"])
    cooldown = timedelta(hours=config.DAILY_BONUS_COOLDOWN_HOURS)
    elapsed = datetime.utcnow() - last_claim

    if elapsed >= cooldown:
        return True, 0.0

    remaining = cooldown - elapsed
    return False, round(remaining.total_seconds() / 3600, 1)


def set_daily_bonus_claimed(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_bonus_claim = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()


# =====================================================================
# TRANSFERS (user to user, atomic with cooldown)
# =====================================================================

def can_transfer(user_id: int):
    """Returns (can_transfer: bool, seconds_remaining: int)."""
    user = get_user(user_id)
    if user is None or user["last_transfer_time"] is None:
        return True, 0

    last = datetime.fromisoformat(user["last_transfer_time"])
    cooldown = timedelta(seconds=config.TRANSFER_COOLDOWN_SECONDS)
    elapsed = datetime.utcnow() - last

    if elapsed >= cooldown:
        return True, 0

    remaining = cooldown - elapsed
    return False, int(remaining.total_seconds())


def transfer_funds(from_id: int, to_id: int, amount: float):
    """Atomically move funds between two users.
    Returns (success: bool, reason: str)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")

        # Conditional debit - fails (rowcount 0) if balance insufficient,
        # preventing negative balances even under concurrent requests.
        cur.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, from_id, amount)
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return False, "insufficient_balance"

        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, to_id))
        cur.execute(
            "UPDATE users SET last_transfer_time = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat(), from_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()

    record_transaction(from_id, "transfer_out", -amount, status="completed")
    record_transaction(to_id, "transfer_in", amount, status="completed")
    return True, "ok"


# =====================================================================
# WITHDRAWALS
# =====================================================================

def create_withdrawal(user_id: int, amount: float, phone: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO withdrawals (user_id, amount, phone, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (user_id, amount, phone, datetime.utcnow().isoformat())
    )
    conn.commit()
    withdrawal_id = cur.lastrowid
    conn.close()
    return withdrawal_id


def get_withdrawal(withdrawal_id: int) -> sqlite3.Row:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_pending_withdrawals() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY created_at ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def update_withdrawal_status(withdrawal_id: int, status: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, withdrawal_id))
    conn.commit()
    conn.close()


# =====================================================================
# DEPOSIT ACCOUNTS (rotating Telebirr numbers)
# =====================================================================

def add_deposit_account(phone: str, recipient_name: str) -> int:
    """Add a new deposit account. If it's the first account, make it active."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM deposit_accounts")
    is_first = cur.fetchone()["c"] == 0

    cur.execute(
        "INSERT INTO deposit_accounts (phone, recipient_name, active, deposit_count, created_at) VALUES (?, ?, ?, 0, ?)",
        (phone, recipient_name, 1 if is_first else 0, datetime.utcnow().isoformat())
    )
    conn.commit()
    account_id = cur.lastrowid
    conn.close()
    return account_id


def remove_deposit_account(account_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT active FROM deposit_accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()
    was_active = row["active"] if row else 0

    cur.execute("DELETE FROM deposit_accounts WHERE id = ?", (account_id,))

    if was_active:
        # Promote another account to active, if any remain
        cur.execute("SELECT id FROM deposit_accounts ORDER BY id LIMIT 1")
        next_row = cur.fetchone()
        if next_row:
            cur.execute("UPDATE deposit_accounts SET active = 1 WHERE id = ?", (next_row["id"],))

    conn.commit()
    conn.close()


def list_deposit_accounts() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM deposit_accounts ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_active_deposit_account() -> sqlite3.Row:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM deposit_accounts WHERE active = 1 LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row


def record_deposit_for_account(account_id: int):
    """Increment the active account's deposit counter. If it reaches the
    rotation threshold, switch the active flag to the next account
    (round-robin by id) and reset this account's counter."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("UPDATE deposit_accounts SET deposit_count = deposit_count + 1 WHERE id = ?", (account_id,))
    cur.execute("SELECT deposit_count FROM deposit_accounts WHERE id = ?", (account_id,))
    row = cur.fetchone()

    if row and row["deposit_count"] >= config.ROTATE_AFTER_DEPOSITS:
        cur.execute("SELECT id FROM deposit_accounts ORDER BY id")
        all_ids = [r["id"] for r in cur.fetchall()]

        if len(all_ids) > 1:
            current_index = all_ids.index(account_id)
            next_id = all_ids[(current_index + 1) % len(all_ids)]

            cur.execute("UPDATE deposit_accounts SET active = 0 WHERE id = ?", (account_id,))
            cur.execute("UPDATE deposit_accounts SET active = 1, deposit_count = 0 WHERE id = ?", (next_id,))
        else:
            # Only one account - just reset its counter
            cur.execute("UPDATE deposit_accounts SET deposit_count = 0 WHERE id = ?", (account_id,))

    conn.commit()
    conn.close()


# =====================================================================
# GAMES
# =====================================================================

def get_or_create_active_game(room_fee: float) -> sqlite3.Row:
    """Get the current waiting/running game for this room fee,
    or create a fresh 'waiting' game if none exists."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM games WHERE room_fee = ? AND state IN ('waiting','running') ORDER BY id DESC LIMIT 1",
        (room_fee,)
    )
    game = cur.fetchone()

    if game is None:
        cur.execute(
            "INSERT INTO games (room_fee, state, pool, created_at) VALUES (?, 'waiting', 0, ?)",
            (room_fee, datetime.utcnow().isoformat())
        )
        conn.commit()
        cur.execute("SELECT * FROM games WHERE id = ?", (cur.lastrowid,))
        game = cur.fetchone()

    conn.close()
    return game


def get_game(game_id: int) -> sqlite3.Row:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM games WHERE id = ?", (game_id,))
    row = cur.fetchone()
    conn.close()
    return row


def set_game_state(game_id: int, state: str):
    conn = get_connection()
    cur = conn.cursor()
    if state == "running":
        cur.execute(
            "UPDATE games SET state = ?, started_at = ? WHERE id = ?",
            (state, datetime.utcnow().isoformat(), game_id)
        )
    else:
        cur.execute("UPDATE games SET state = ? WHERE id = ?", (state, game_id))
    conn.commit()
    conn.close()


def finish_game(game_id: int, winner_ids: list, house_cut: float, per_winner_amount: float):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE games SET state = 'finished', winner_ids = ?, house_cut = ?, "
        "per_winner_amount = ?, finished_at = ? WHERE id = ?",
        (json.dumps(winner_ids), house_cut, per_winner_amount, datetime.utcnow().isoformat(), game_id)
    )
    conn.commit()
    conn.close()


def get_pool(game_id: int) -> float:
    game = get_game(game_id)
    return game["pool"] if game else 0.0


# =====================================================================
# GAME PLAYERS
# =====================================================================

def upsert_game_player_message(game_id: int, user_id: int, chat_id: int, message_id: int):
    """Store/update where this player's live game message lives, so the
    number-calling loop can edit it directly."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM game_players WHERE game_id = ? AND user_id = ?", (game_id, user_id))
    row = cur.fetchone()

    if row:
        cur.execute(
            "UPDATE game_players SET chat_id = ?, message_id = ? WHERE game_id = ? AND user_id = ?",
            (chat_id, message_id, game_id, user_id)
        )
    else:
        cur.execute(
            "INSERT INTO game_players (game_id, user_id, cards_count, auto_win, chat_id, message_id, created_at) "
            "VALUES (?, ?, 0, 0, ?, ?, ?)",
            (game_id, user_id, chat_id, message_id, datetime.utcnow().isoformat())
        )
    conn.commit()
    conn.close()


def get_game_player(game_id: int, user_id: int) -> sqlite3.Row:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM game_players WHERE game_id = ? AND user_id = ?", (game_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row


def get_game_players(game_id: int) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM game_players WHERE game_id = ? ORDER BY id ASC", (game_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def set_auto_win(game_id: int, user_id: int, value: bool):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE game_players SET auto_win = ? WHERE game_id = ? AND user_id = ?",
        (1 if value else 0, game_id, user_id)
    )
    conn.commit()
    conn.close()


# =====================================================================
# GAME CARDS
# =====================================================================

def get_taken_cards(game_id: int) -> set:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT card_index FROM game_cards WHERE game_id = ?", (game_id,))
    rows = cur.fetchall()
    conn.close()
    return {r["card_index"] for r in rows}


def get_player_cards(game_id: int, user_id: int) -> list:
    """Returns list of card_index values owned by this user in this game, ordered."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT card_index FROM game_cards WHERE game_id = ? AND owner_id = ? ORDER BY card_index ASC",
        (game_id, user_id)
    )
    rows = cur.fetchall()
    conn.close()
    return [r["card_index"] for r in rows]


def count_cards_sold(game_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM game_cards WHERE game_id = ?", (game_id,))
    row = cur.fetchone()
    conn.close()
    return row["c"]


def get_all_game_cards(game_id: int) -> list:
    """Returns all cards in a game with owner info - used for refunds / payouts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM game_cards WHERE game_id = ?", (game_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def update_marked_numbers(game_id: int, card_index: int, marked_list: list):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE game_cards SET marked_numbers = ? WHERE game_id = ? AND card_index = ?",
        (json.dumps(marked_list), game_id, card_index)
    )
    conn.commit()
    conn.close()


def get_marked_numbers(game_id: int, card_index: int) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT marked_numbers FROM game_cards WHERE game_id = ? AND card_index = ?",
        (game_id, card_index)
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return []
    return json.loads(row["marked_numbers"])


def purchase_cards(game_id: int, user_id: int, card_indices: list, fee_per_card: float):
    """Atomically purchase one or more cards for a game.

    Validates:
      - sufficient balance for total cost
      - none of the requested cards are already taken (UNIQUE constraint)
      - player's total cards in this game won't exceed MAX_CARDS_PER_PLAYER

    On success: deducts balance, adds to the game pool, records ownership,
    and updates/creates the game_players row.

    Returns (success: bool, reason: str)
      reason in {"ok", "insufficient_balance", "card_taken", "max_cards_exceeded"}
    """
    total_cost = fee_per_card * len(card_indices)
    now = datetime.utcnow().isoformat()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")

        # --- Check max cards per player ---
        cur.execute("SELECT cards_count FROM game_players WHERE game_id = ? AND user_id = ?", (game_id, user_id))
        gp = cur.fetchone()
        existing_count = gp["cards_count"] if gp else 0

        if existing_count + len(card_indices) > config.MAX_CARDS_PER_PLAYER:
            conn.rollback()
            conn.close()
            return False, "max_cards_exceeded"

        # --- Conditional balance debit (atomic, prevents negative balance) ---
        cur.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (total_cost, user_id, total_cost)
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return False, "insufficient_balance"

        # --- Insert cards (UNIQUE constraint prevents double-selling) ---
        for card_index in card_indices:
            cur.execute(
                "INSERT INTO game_cards (game_id, card_index, owner_id, marked_numbers, created_at) "
                "VALUES (?, ?, ?, '[]', ?)",
                (game_id, card_index, user_id, now)
            )

        # --- Update pool ---
        cur.execute("UPDATE games SET pool = pool + ? WHERE id = ?", (total_cost, game_id))

        # --- Upsert game_players ---
        if gp is None:
            cur.execute(
                "INSERT INTO game_players (game_id, user_id, cards_count, auto_win, created_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (game_id, user_id, len(card_indices), now)
            )
        else:
            cur.execute(
                "UPDATE game_players SET cards_count = cards_count + ? WHERE game_id = ? AND user_id = ?",
                (len(card_indices), game_id, user_id)
            )

        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return False, "card_taken"
    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()
    record_transaction(user_id, "bingo_bet", -total_cost, status="completed")
    return True, "ok"


def refund_game(game_id: int):
    """Refund every player for every card they bought in this game.
    Used when <2 cards sold at countdown end, or no winner after 75 calls."""
    cards = get_all_game_cards(game_id)
    game = get_game(game_id)
    fee = game["room_fee"]

    refunded = {}
    for card in cards:
        owner = card["owner_id"]
        refunded[owner] = refunded.get(owner, 0) + fee

    for user_id, amount in refunded.items():
        adjust_balance(user_id, amount)
        record_transaction(user_id, "bingo_refund", amount, status="completed")

    return refunded  # {user_id: amount_refunded}


# =====================================================================
# GAME NUMBERS (call sequence)
# =====================================================================

def add_called_number(game_id: int, call_order: int, number: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO game_numbers (game_id, call_order, number, called_at) VALUES (?, ?, ?, ?)",
        (game_id, call_order, number, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_called_numbers(game_id: int) -> list:
    """Returns the called numbers in call order."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT number FROM game_numbers WHERE game_id = ? ORDER BY call_order ASC", (game_id,))
    rows = cur.fetchall()
    conn.close()
    return [r["number"] for r in rows]


def get_call_count(game_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM game_numbers WHERE game_id = ?", (game_id,))
    row = cur.fetchone()
    conn.close()
    return row["c"]


# =====================================================================
# =====================================================================
# ADMIN DASHBOARD AGGREGATES
# =====================================================================

def get_total_games_played() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM games WHERE state = 'finished'")
    row = cur.fetchone()
    conn.close()
    return row["c"]


def get_total_unique_players() -> int:
    """Number of distinct users who have ever bought a bingo card."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT owner_id) as c FROM game_cards")
    row = cur.fetchone()
    conn.close()
    return row["c"]


# =====================================================================
# HOUSE WALLET
# Single-row table tracking cumulative house commission.
# Admin can view and withdraw from it via /admin panel.
# =====================================================================

def init_house_wallet():
    """Ensure house_wallet table and its single row exist.
    Called inside init_db() automatically."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS house_wallet (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL NOT NULL DEFAULT 0,
            total_earned REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        INSERT OR IGNORE INTO house_wallet (id, balance, total_earned, updated_at)
        VALUES (1, 0, 0, ?)
    """, (datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()


def get_house_balance() -> float:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM house_wallet WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["balance"] if row else 0.0


def get_house_total_earned() -> float:
    """Cumulative all-time commission - never decreases."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT total_earned FROM house_wallet WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row["total_earned"] if row else 0.0


def add_house_commission(amount: float) -> float:
    """Credit the house wallet. Returns new balance."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE house_wallet
        SET balance = balance + ?,
            total_earned = total_earned + ?,
            updated_at = ?
        WHERE id = 1
    """, (amount, amount, datetime.utcnow().isoformat()))
    conn.commit()
    cur.execute("SELECT balance FROM house_wallet WHERE id = 1")
    new_balance = cur.fetchone()["balance"]
    conn.close()
    return new_balance


def credit_house(amount: float) -> float:
    """Credit the house wallet AND record a house_commission ledger entry.
    Call once per finished game with that game's house cut.
    Returns the new house wallet balance."""
    new_balance = add_house_commission(amount)
    record_transaction(config.HOUSE_ACCOUNT_ID, "house_commission", amount, status="completed")
    return new_balance


def withdraw_house_funds(amount: float):
    """Deduct from house wallet. Returns (success, reason, new_balance)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT balance FROM house_wallet WHERE id = 1")
    row = cur.fetchone()
    if row is None or row["balance"] < amount:
        conn.rollback()
        conn.close()
        return False, "insufficient_house_balance", 0.0

    cur.execute("""
        UPDATE house_wallet SET balance = balance - ?, updated_at = ?
        WHERE id = 1
    """, (amount, datetime.utcnow().isoformat()))
    conn.commit()
    cur.execute("SELECT balance FROM house_wallet WHERE id = 1")
    new_bal = cur.fetchone()["balance"]
    conn.close()
    return True, "ok", new_bal
