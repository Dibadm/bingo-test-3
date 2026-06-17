"""
database.py — Async SQLite layer for Habesha Bet Bingo Bot.
All money operations use IMMEDIATE transactions to prevent race conditions.
"""

import aiosqlite
import json
import time
import secrets
import string
from typing import Optional, Any

import config


# ── Connection helper ──────────────────────────────────────────────────────────

async def _conn() -> aiosqlite.Connection:
    db = await aiosqlite.connect(config.DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


def _row(row) -> Optional[dict]:
    return dict(row) if row else None


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _ref_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(8))


# ── Schema ─────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables on startup."""
    async with await _conn() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id     INTEGER UNIQUE NOT NULL,
                username        TEXT    DEFAULT '',
                first_name      TEXT    DEFAULT '',
                phone           TEXT    DEFAULT '',
                balance         REAL    DEFAULT 0.0,
                language        TEXT    DEFAULT 'en',
                referral_code   TEXT    UNIQUE,
                referred_by     INTEGER DEFAULT NULL,
                last_transfer_at REAL   DEFAULT 0,
                games_played    INTEGER DEFAULT 0,
                total_won       REAL    DEFAULT 0.0,
                created_at      REAL    DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS deposit_accounts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                phone          TEXT    NOT NULL,
                name           TEXT    NOT NULL,
                is_active      INTEGER DEFAULT 1,
                deposit_count  INTEGER DEFAULT 0,
                created_at     REAL    DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                type       TEXT    NOT NULL,
                amount     REAL    NOT NULL,
                reference  TEXT    DEFAULT '',
                status     TEXT    DEFAULT 'completed',
                note       TEXT    DEFAULT '',
                created_at REAL    DEFAULT (unixepoch()),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                amount      REAL    NOT NULL,
                phone       TEXT    NOT NULL,
                status      TEXT    DEFAULT 'pending',
                tx_id       INTEGER DEFAULT NULL,
                admin_note  TEXT    DEFAULT '',
                created_at  REAL    DEFAULT (unixepoch()),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS games (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                room_fee         INTEGER NOT NULL,
                status           TEXT    DEFAULT 'lobby',
                prize_pool       REAL    DEFAULT 0.0,
                called_numbers   TEXT    DEFAULT '[]',
                winner_ids       TEXT    DEFAULT '[]',
                prize_per_winner REAL    DEFAULT 0.0,
                house_cut        REAL    DEFAULT 0.0,
                created_at       REAL    DEFAULT (unixepoch()),
                started_at       REAL    DEFAULT NULL,
                finished_at      REAL    DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS game_cards (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                card_number INTEGER NOT NULL,
                numbers     TEXT    NOT NULL,
                is_winner   INTEGER DEFAULT 0,
                win_type    TEXT    DEFAULT '',
                created_at  REAL    DEFAULT (unixepoch()),
                FOREIGN KEY (game_id) REFERENCES games(id),
                UNIQUE(game_id, card_number)
            );

            CREATE TABLE IF NOT EXISTS used_tx_refs (
                ref        TEXT PRIMARY KEY,
                created_at REAL DEFAULT (unixepoch())
            );
        """)
        await db.commit()
    # Seed default deposit accounts if none exist
    await _seed_deposit_accounts()


async def _seed_deposit_accounts() -> None:
    async with await _conn() as db:
        row = await db.execute_fetchone("SELECT COUNT(*) AS c FROM deposit_accounts")
        if row and row["c"] == 0:
            for acct in config.DEFAULT_TELEBIRR_ACCOUNTS:
                await db.execute(
                    "INSERT INTO deposit_accounts (phone, name) VALUES (?, ?)",
                    (acct["phone"], acct["name"])
                )
            await db.commit()


# ── Users ──────────────────────────────────────────────────────────────────────

async def get_or_create_user(
    telegram_id: int,
    username: str = "",
    first_name: str = "",
) -> dict:
    async with await _conn() as db:
        row = _row(await db.execute_fetchone(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ))
        if row:
            # Update name/username on every visit
            await db.execute(
                "UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                (username, first_name, telegram_id)
            )
            await db.commit()
            row["username"] = username
            row["first_name"] = first_name
            return row

        code = _ref_code()
        await db.execute(
            """INSERT INTO users (telegram_id, username, first_name, referral_code)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, username, first_name, code)
        )
        await db.commit()
        return _row(await db.execute_fetchone(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ))


async def get_user(telegram_id: int) -> Optional[dict]:
    async with await _conn() as db:
        return _row(await db.execute_fetchone(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ))


async def get_user_by_username(username: str) -> Optional[dict]:
    uname = username.lstrip("@")
    async with await _conn() as db:
        return _row(await db.execute_fetchone(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (uname,)
        ))


async def set_phone(telegram_id: int, phone: str) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE users SET phone=? WHERE telegram_id=?", (phone, telegram_id)
        )
        await db.commit()


async def set_language(telegram_id: int, lang: str) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE users SET language=? WHERE telegram_id=?", (lang, telegram_id)
        )
        await db.commit()


async def update_last_transfer(telegram_id: int) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE users SET last_transfer_at=? WHERE telegram_id=?",
            (time.time(), telegram_id)
        )
        await db.commit()


# ── Balance operations (IMMEDIATE transactions) ───────────────────────────────

async def add_balance(
    telegram_id: int,
    amount: float,
    tx_type: str = "deposit",
    reference: str = "",
    note: str = "",
) -> float:
    """Credit amount to user. Returns new balance."""
    async with await _conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
            (amount, telegram_id)
        )
        user_row = _row(await db.execute_fetchone(
            "SELECT id, balance FROM users WHERE telegram_id = ?", (telegram_id,)
        ))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, reference, note) VALUES (?,?,?,?,?)",
            (user_row["id"], tx_type, amount, reference, note)
        )
        await db.commit()
        return user_row["balance"]


async def deduct_balance(
    telegram_id: int,
    amount: float,
    tx_type: str = "card_buy",
    note: str = "",
) -> tuple[bool, float]:
    """Debit amount from user. Returns (success, new_balance)."""
    async with await _conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        row = _row(await db.execute_fetchone(
            "SELECT id, balance FROM users WHERE telegram_id = ?", (telegram_id,)
        ))
        if not row or row["balance"] < amount - 0.001:
            await db.execute("ROLLBACK")
            return False, row["balance"] if row else 0.0
        new_bal = row["balance"] - amount
        await db.execute(
            "UPDATE users SET balance = ? WHERE telegram_id = ?", (new_bal, telegram_id)
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (row["id"], tx_type, -amount, note)
        )
        await db.commit()
        return True, new_bal


async def transfer_balance(
    from_tid: int,
    to_tid: int,
    amount: float,
) -> tuple[bool, str]:
    """Atomic balance transfer. Returns (success, error_msg)."""
    async with await _conn() as db:
        await db.execute("BEGIN IMMEDIATE")
        fr = _row(await db.execute_fetchone(
            "SELECT id, balance FROM users WHERE telegram_id=?", (from_tid,)
        ))
        to = _row(await db.execute_fetchone(
            "SELECT id, balance FROM users WHERE telegram_id=?", (to_tid,)
        ))
        if not fr:
            await db.execute("ROLLBACK")
            return False, "sender_not_found"
        if not to:
            await db.execute("ROLLBACK")
            return False, "recipient_not_found"
        if fr["balance"] < amount - 0.001:
            await db.execute("ROLLBACK")
            return False, "insufficient_balance"
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, from_tid)
        )
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, to_tid)
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (fr["id"], "transfer_out", -amount, f"to:{to_tid}")
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (to["id"], "transfer_in", amount, f"from:{from_tid}")
        )
        await db.execute(
            "UPDATE users SET last_transfer_at=? WHERE telegram_id=?", (time.time(), from_tid)
        )
        await db.commit()
        return True, ""


# ── Deposit accounts & TX refs ─────────────────────────────────────────────────

async def get_active_deposit_account() -> Optional[dict]:
    """Return the currently active deposit account (rotating by DEPOSITS_PER_ROTATION)."""
    async with await _conn() as db:
        rows = _rows(await (await db.execute(
            "SELECT * FROM deposit_accounts WHERE is_active=1 ORDER BY id"
        )).fetchall())
        if not rows:
            return None
        for acct in rows:
            if acct["deposit_count"] < config.DEPOSITS_PER_ROTATION:
                return acct
        # All rotated — reset the first one
        await db.execute("UPDATE deposit_accounts SET deposit_count=0 WHERE id=?", (rows[0]["id"],))
        await db.commit()
        return rows[0]


async def increment_account_deposits(account_id: int) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE deposit_accounts SET deposit_count=deposit_count+1 WHERE id=?",
            (account_id,)
        )
        await db.commit()


async def is_ref_used(ref: str) -> bool:
    async with await _conn() as db:
        row = await db.execute_fetchone(
            "SELECT 1 FROM used_tx_refs WHERE ref=?", (ref,)
        )
        return row is not None


async def mark_ref_used(ref: str) -> None:
    async with await _conn() as db:
        await db.execute("INSERT OR IGNORE INTO used_tx_refs (ref) VALUES (?)", (ref,))
        await db.commit()


async def get_deposit_accounts() -> list[dict]:
    async with await _conn() as db:
        return _rows(await (await db.execute(
            "SELECT * FROM deposit_accounts ORDER BY id"
        )).fetchall())


async def add_deposit_account(phone: str, name: str) -> int:
    async with await _conn() as db:
        cur = await db.execute(
            "INSERT INTO deposit_accounts (phone, name) VALUES (?,?)", (phone, name)
        )
        await db.commit()
        return cur.lastrowid


async def remove_deposit_account(acct_id: int) -> None:
    async with await _conn() as db:
        await db.execute("UPDATE deposit_accounts SET is_active=0 WHERE id=?", (acct_id,))
        await db.commit()


# ── Games ──────────────────────────────────────────────────────────────────────

async def create_game(room_fee: int) -> int:
    async with await _conn() as db:
        cur = await db.execute(
            "INSERT INTO games (room_fee) VALUES (?)", (room_fee,)
        )
        await db.commit()
        return cur.lastrowid


async def get_active_game(room_fee: int) -> Optional[dict]:
    async with await _conn() as db:
        return _row(await db.execute_fetchone(
            "SELECT * FROM games WHERE room_fee=? AND status IN ('lobby','countdown','running') ORDER BY id DESC LIMIT 1",
            (room_fee,)
        ))


async def set_game_status(game_id: int, status: str) -> None:
    ts = time.time()
    async with await _conn() as db:
        if status == "running":
            await db.execute(
                "UPDATE games SET status=?, started_at=? WHERE id=?", (status, ts, game_id)
            )
        elif status == "finished":
            await db.execute(
                "UPDATE games SET status=?, finished_at=? WHERE id=?", (status, ts, game_id)
            )
        else:
            await db.execute("UPDATE games SET status=? WHERE id=?", (status, game_id))
        await db.commit()


async def update_game_pool(game_id: int, pool: float) -> None:
    async with await _conn() as db:
        await db.execute("UPDATE games SET prize_pool=? WHERE id=?", (pool, game_id))
        await db.commit()


async def update_called_numbers(game_id: int, numbers: list[int]) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE games SET called_numbers=? WHERE id=?",
            (json.dumps(numbers), game_id)
        )
        await db.commit()


async def finish_game(
    game_id: int,
    winner_tids: list[int],
    prize_per_winner: float,
    house_cut: float,
) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE games SET status='finished', finished_at=?, winner_ids=?, prize_per_winner=?, house_cut=? WHERE id=?",
            (time.time(), json.dumps(winner_tids), prize_per_winner, house_cut, game_id)
        )
        # Credit winners
        for tid in winner_tids:
            user = _row(await db.execute_fetchone(
                "SELECT id FROM users WHERE telegram_id=?", (tid,)
            ))
            if user:
                await db.execute(
                    "UPDATE users SET balance=balance+?, games_played=games_played+1, total_won=total_won+? WHERE telegram_id=?",
                    (prize_per_winner, prize_per_winner, tid)
                )
                await db.execute(
                    "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                    (user["id"], "win", prize_per_winner, f"game:{game_id}")
                )
        # Update games_played for non-winners too
        card_users = _rows(await (await db.execute(
            "SELECT DISTINCT user_id FROM game_cards WHERE game_id=?", (game_id,)
        )).fetchall())
        for cu in card_users:
            # user_id here is telegram_id (see add_game_card below)
            if cu["user_id"] not in winner_tids:
                await db.execute(
                    "UPDATE users SET games_played=games_played+1 WHERE telegram_id=?",
                    (cu["user_id"],)
                )
        await db.commit()


async def refund_game(game_id: int) -> list[tuple[int, float]]:
    """Refund all card purchases for a game. Returns list of (telegram_id, refund_amount)."""
    async with await _conn() as db:
        cards = _rows(await (await db.execute(
            "SELECT user_id, COUNT(*) as cnt FROM game_cards WHERE game_id=? GROUP BY user_id",
            (game_id,)
        )).fetchall())
        game = _row(await db.execute_fetchone("SELECT room_fee FROM games WHERE id=?", (game_id,)))
        if not game:
            return []
        fee = game["room_fee"]
        refunds = []
        for card in cards:
            tid = card["user_id"]
            amount = card["cnt"] * fee
            user = _row(await db.execute_fetchone(
                "SELECT id FROM users WHERE telegram_id=?", (tid,)
            ))
            if user:
                await db.execute(
                    "UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, tid)
                )
                await db.execute(
                    "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                    (user["id"], "refund", amount, f"game:{game_id}")
                )
                refunds.append((tid, amount))
        await db.execute(
            "UPDATE games SET status='finished', finished_at=? WHERE id=?",
            (time.time(), game_id)
        )
        await db.commit()
        return refunds


# ── Game cards ─────────────────────────────────────────────────────────────────

async def add_game_card(
    game_id: int,
    telegram_id: int,
    card_number: int,
    grid: list[list[int]],
) -> bool:
    """Try to reserve a card. Returns False if already taken."""
    try:
        async with await _conn() as db:
            await db.execute(
                "INSERT INTO game_cards (game_id, user_id, card_number, numbers) VALUES (?,?,?,?)",
                (game_id, telegram_id, card_number, json.dumps(grid))
            )
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def get_game_cards(
    game_id: int,
    telegram_id: Optional[int] = None,
) -> list[dict]:
    async with await _conn() as db:
        if telegram_id is not None:
            rows = await (await db.execute(
                "SELECT * FROM game_cards WHERE game_id=? AND user_id=? ORDER BY card_number",
                (game_id, telegram_id)
            )).fetchall()
        else:
            rows = await (await db.execute(
                "SELECT * FROM game_cards WHERE game_id=? ORDER BY card_number",
                (game_id,)
            )).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["numbers"] = json.loads(d["numbers"])
            result.append(d)
        return result


async def get_card_owners(game_id: int) -> dict[int, int]:
    """Returns {card_number: telegram_id} for all sold cards in a game."""
    async with await _conn() as db:
        rows = await (await db.execute(
            "SELECT card_number, user_id FROM game_cards WHERE game_id=?", (game_id,)
        )).fetchall()
        return {r["card_number"]: r["user_id"] for r in rows}


async def mark_card_winner(game_id: int, card_number: int, win_type: str) -> None:
    async with await _conn() as db:
        await db.execute(
            "UPDATE game_cards SET is_winner=1, win_type=? WHERE game_id=? AND card_number=?",
            (win_type, game_id, card_number)
        )
        await db.commit()


# ── Withdrawals ────────────────────────────────────────────────────────────────

async def create_withdrawal(telegram_id: int, amount: float, phone: str) -> int:
    async with await _conn() as db:
        user = _row(await db.execute_fetchone(
            "SELECT id FROM users WHERE telegram_id=?", (telegram_id,)
        ))
        if not user:
            raise ValueError("user not found")
        ok, _ = await deduct_balance(telegram_id, amount, "withdraw", "withdrawal pending")
        if not ok:
            raise ValueError("insufficient_balance")
        cur = await db.execute(
            "INSERT INTO withdrawals (user_id, telegram_id, amount, phone) VALUES (?,?,?,?)",
            (user["id"], telegram_id, amount, phone)
        )
        await db.commit()
        return cur.lastrowid


async def get_pending_withdrawals() -> list[dict]:
    async with await _conn() as db:
        rows = await (await db.execute(
            """SELECT w.*, u.username, u.first_name FROM withdrawals w
               JOIN users u ON u.telegram_id = w.telegram_id
               WHERE w.status='pending' ORDER BY w.created_at"""
        )).fetchall()
        return _rows(rows)


async def approve_withdrawal(wd_id: int) -> Optional[dict]:
    async with await _conn() as db:
        wd = _row(await db.execute_fetchone(
            "SELECT * FROM withdrawals WHERE id=?", (wd_id,)
        ))
        if not wd or wd["status"] != "pending":
            return None
        await db.execute(
            "UPDATE withdrawals SET status='approved' WHERE id=?", (wd_id,)
        )
        await db.commit()
        return wd


async def reject_withdrawal(wd_id: int) -> Optional[dict]:
    async with await _conn() as db:
        wd = _row(await db.execute_fetchone(
            "SELECT * FROM withdrawals WHERE id=?", (wd_id,)
        ))
        if not wd or wd["status"] != "pending":
            return None
        await db.execute(
            "UPDATE withdrawals SET status='rejected' WHERE id=?", (wd_id,)
        )
        # Refund balance
        user = _row(await db.execute_fetchone(
            "SELECT id FROM users WHERE telegram_id=?", (wd["telegram_id"],)
        ))
        if user:
            await db.execute(
                "UPDATE users SET balance=balance+? WHERE telegram_id=?",
                (wd["amount"], wd["telegram_id"])
            )
            await db.execute(
                "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                (user["id"], "refund", wd["amount"], f"wd_reject:{wd_id}")
            )
        await db.commit()
        return wd


# ── Transactions history ───────────────────────────────────────────────────────

async def get_user_transactions(telegram_id: int, limit: int = 10) -> list[dict]:
    async with await _conn() as db:
        user = _row(await db.execute_fetchone(
            "SELECT id FROM users WHERE telegram_id=?", (telegram_id,)
        ))
        if not user:
            return []
        rows = await (await db.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user["id"], limit)
        )).fetchall()
        return _rows(rows)


# ── Admin stats ────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    async with await _conn() as db:
        users = (await db.execute_fetchone("SELECT COUNT(*) AS c FROM users"))["c"]
        games = (await db.execute_fetchone("SELECT COUNT(*) AS c FROM games WHERE status='finished'"))["c"]
        collected_row = await db.execute_fetchone(
            "SELECT COALESCE(SUM(prize_pool),0) AS s FROM games WHERE status='finished'"
        )
        collected = collected_row["s"] if collected_row else 0.0
        profit_row = await db.execute_fetchone(
            "SELECT COALESCE(SUM(house_cut),0) AS s FROM games WHERE status='finished'"
        )
        profit = profit_row["s"] if profit_row else 0.0
        pending_wd = (await db.execute_fetchone(
            "SELECT COUNT(*) AS c FROM withdrawals WHERE status='pending'"
        ))["c"]
        return {
            "users": users,
            "games": games,
            "collected": round(collected, 2),
            "profit": round(profit, 2),
            "pending_wd": pending_wd,
        }


async def get_all_user_tids() -> list[int]:
    async with await _conn() as db:
        rows = await (await db.execute("SELECT telegram_id FROM users")).fetchall()
        return [r["telegram_id"] for r in rows]


async def get_user_referral_count(telegram_id: int) -> int:
    async with await _conn() as db:
        user = _row(await db.execute_fetchone(
            "SELECT id FROM users WHERE telegram_id=?", (telegram_id,)
        ))
        if not user:
            return 0
        row = await db.execute_fetchone(
            "SELECT COUNT(*) AS c FROM users WHERE referred_by=?", (user["id"],)
        )
        return row["c"] if row else 0


async def set_referred_by(new_user_tid: int, referrer_tid: int) -> None:
    """Record referral link. Awards bonus to both parties."""
    async with await _conn() as db:
        referrer = _row(await db.execute_fetchone(
            "SELECT id FROM users WHERE telegram_id=?", (referrer_tid,)
        ))
        new_user = _row(await db.execute_fetchone(
            "SELECT id, referred_by FROM users WHERE telegram_id=?", (new_user_tid,)
        ))
        if not referrer or not new_user or new_user["referred_by"]:
            return
        await db.execute(
            "UPDATE users SET referred_by=? WHERE telegram_id=?",
            (referrer["id"], new_user_tid)
        )
        await db.commit()
    # Award bonus
    bonus = config.REFERRAL_BONUS
    await add_balance(referrer_tid, bonus, "referral", note=f"ref:{new_user_tid}")
    await add_balance(new_user_tid, bonus, "referral", note=f"ref_by:{referrer_tid}")
