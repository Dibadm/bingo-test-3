#!/usr/bin/env python3
"""
bot.py — Habesha Bet Bingo Bot main module.
python-telegram-bot v20 | asyncio | SQLite
"""

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Optional

from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters,
)

import config
import database as db
from bingo import generate_unique_cards, check_win, render_card_text, render_number_grid, to_amharic
from locales import get_text
from sms_parser import parse_telebirr_sms, verify_recipient, verify_amount

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────────
PHONE_INPUT = 10
DEPOSIT_AMOUNT, DEPOSIT_SMS = 20, 21
WITHDRAW_AMOUNT = 30
TRANSFER_USER, TRANSFER_AMOUNT = 40, 41
ADMIN_BROADCAST = 50
ADMIN_ACCOUNTS = 51

# ── Global game state ──────────────────────────────────────────────────────────
# One entry per room fee. Holds all volatile state for a running game.
GAMES: dict[int, dict] = {}


def _empty_room() -> dict:
    return {
        "game_id": None,
        "status": "lobby",         # lobby | countdown | running | finished
        "card_owners": {},          # {card_num: telegram_id}
        "user_cards": {},           # {telegram_id: [card_num, ...]}
        "all_card_grids": {},       # {card_num: grid}   populated at game start
        "prize_pool": 0.0,
        "called_numbers": [],
        "participants": set(),
        "countdown_task": None,
        "call_task": None,
        "auto_win_users": set(),    # telegram_ids with auto-win ON
        "game_messages": {},        # {telegram_id: message_id}
        "countdown_remaining": config.COUNTDOWN_SECONDS,
        "last_buyer_name": "—",
    }


def _init_all_rooms() -> None:
    for fee in config.ROOM_FEES:
        GAMES[fee] = _empty_room()


# ── Helpers ────────────────────────────────────────────────────────────────────

def lang(user: dict) -> str:
    return user.get("language", "en")


def t(key: str, user: dict, **kw) -> str:
    return get_text(key, lang(user), **kw)


def mask_name(first: str, username: str) -> str:
    if first:
        return first[:1] + "***"
    if username:
        return "@" + username[:2] + "***"
    return "***"


async def safe_edit(bot: Bot, chat_id: int, message_id: int, text: str, markup=None) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except (BadRequest, Forbidden):
        pass


async def safe_send(bot: Bot, chat_id: int, text: str, markup=None) -> Optional[int]:
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return msg.message_id
    except (BadRequest, Forbidden):
        return None


# ── UI builders ────────────────────────────────────────────────────────────────

def main_menu_markup(user: dict) -> InlineKeyboardMarkup:
    L = lang(user)
    rows = [
        [InlineKeyboardButton(get_text("btn_play", L), callback_data="games")],
        [
            InlineKeyboardButton(get_text("btn_deposit", L), callback_data="deposit"),
            InlineKeyboardButton(get_text("btn_withdraw", L), callback_data="withdraw"),
        ],
        [
            InlineKeyboardButton(get_text("btn_transfer", L), callback_data="transfer"),
            InlineKeyboardButton(get_text("btn_profile", L), callback_data="profile"),
        ],
        [
            InlineKeyboardButton(get_text("btn_transactions", L), callback_data="transactions"),
            InlineKeyboardButton(get_text("btn_balance", L), callback_data="balance"),
        ],
        [
            InlineKeyboardButton(get_text("btn_group", L), url=config.GROUP_LINK),
            InlineKeyboardButton(get_text("btn_contact", L), url=f"https://t.me/{config.CONTACT_USERNAME.lstrip('@')}"),
        ],
        [
            InlineKeyboardButton(get_text("btn_refer", L), callback_data="referral"),
            InlineKeyboardButton(get_text("btn_language", L), callback_data="toggle_lang"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def rooms_markup(user: dict) -> InlineKeyboardMarkup:
    L = lang(user)
    rows = []
    for fee in config.ROOM_FEES:
        g = GAMES[fee]
        pool = round(g["prize_pool"] * (1 - config.HOUSE_COMMISSION), 2)
        sold = len(g["card_owners"])
        rows.append([InlineKeyboardButton(
            f"🎯 {fee} ETB | 🏆 {pool} ETB | 👥 {sold} cards",
            callback_data=f"room:{fee}",
        )])
    rows.append([InlineKeyboardButton(get_text("btn_back", L), callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def card_selection_markup(
    room_fee: int,
    page: int,
    user_tid: int,
    user: dict,
) -> InlineKeyboardMarkup:
    """Build the paginated card selection keyboard."""
    L = lang(user)
    g = GAMES[room_fee]
    card_owners = g["card_owners"]
    my_cards = set(g["user_cards"].get(user_tid, []))

    per_page = config.CARDS_PER_PAGE   # 50
    total_pages = (config.TOTAL_CARDS + per_page - 1) // per_page  # 4
    start = page * per_page + 1
    end = min(start + per_page - 1, config.TOTAL_CARDS)

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for card_num in range(start, end + 1):
        owner = card_owners.get(card_num)
        if card_num in my_cards:
            label = f"✅{card_num}"
        elif owner is not None:
            label = f"⬛{card_num}"
        else:
            label = str(card_num)
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"card_toggle:{room_fee}:{card_num}:{page}",
        ))
        if len(row) == 10:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Navigation
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀", callback_data=f"card_page:{room_fee}:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶", callback_data=f"card_page:{room_fee}:{page+1}"))
    rows.append(nav)

    # Actions
    n_sel = len(my_cards)
    cost = n_sel * room_fee
    action_row = [
        InlineKeyboardButton("🎲 x1", callback_data=f"rand_card:{room_fee}:{page}:1"),
        InlineKeyboardButton("🎲 x2", callback_data=f"rand_card:{room_fee}:{page}:2"),
    ]
    if n_sel > 0:
        action_row.append(InlineKeyboardButton(
            f"▶️ START! ({n_sel}×{room_fee}={cost}ETB)",
            callback_data=f"buy_cards:{room_fee}",
        ))
    rows.append(action_row)
    rows.append([InlineKeyboardButton(get_text("btn_back", L), callback_data="rooms")])
    return InlineKeyboardMarkup(rows)


def card_selection_text(room_fee: int, user_tid: int, user: dict) -> str:
    g = GAMES[room_fee]
    sold = len(g["card_owners"])
    pool = round(g["prize_pool"] * (1 - config.HOUSE_COMMISSION), 2)
    timer = g["countdown_remaining"] if g["status"] == "countdown" else "—"
    return t("card_selection", user,
             fee=room_fee,
             balance=round(user.get("balance", 0), 2),
             pool=pool,
             sold=sold,
             timer=timer,
             last=g["last_buyer_name"],
             max=config.MAX_CARDS_PER_PLAYER)


def game_screen_text(room_fee: int, user: dict) -> str:
    g = GAMES[room_fee]
    called = g["called_numbers"]
    last_num = called[-1] if called else "—"
    grid_html = render_number_grid(called)
    pool = round(g["prize_pool"] * (1 - config.HOUSE_COMMISSION), 2)
    return t("game_screen", user,
             fee=room_fee,
             pool=pool,
             players=len(g["participants"]),
             called=len(called),
             last_num=last_num,
             number_grid=grid_html)


def game_screen_markup(room_fee: int, user_tid: int, user: dict) -> InlineKeyboardMarkup:
    g = GAMES[room_fee]
    L = lang(user)
    my_cards = g["user_cards"].get(user_tid, [])
    called_set = set(g["called_numbers"])
    # Count marked cells across all user cards
    marked_total = 0
    total_cells = 0
    for card_num in my_cards:
        grid = g["all_card_grids"].get(card_num, [])
        for row in grid:
            for n in row:
                total_cells += 1
                if n == 0 or n in called_set:
                    marked_total += 1

    auto_on = user_tid in g["auto_win_users"]
    auto_lbl = get_text("btn_auto_on" if auto_on else "btn_auto_off", L)
    rows = [
        [
            InlineKeyboardButton(auto_lbl, callback_data=f"auto_win:{room_fee}"),
            InlineKeyboardButton(
                get_text("btn_check", L, n=marked_total, total=total_cells),
                callback_data=f"check_win:{room_fee}",
            ),
        ],
        [InlineKeyboardButton(get_text("btn_bingo", L), callback_data=f"claim_bingo:{room_fee}")],
    ]
    return InlineKeyboardMarkup(rows)


# ── Game engine ────────────────────────────────────────────────────────────────

async def ensure_game_for_room(app: Application, room_fee: int) -> int:
    """Make sure a lobby game exists for the room in DB and memory. Returns game_id."""
    g = GAMES[room_fee]
    if g["game_id"] is None:
        game_id = await db.create_game(room_fee)
        g["game_id"] = game_id
        # Pre-generate all 200 card grids for this game
        cards = generate_unique_cards(config.TOTAL_CARDS, seed=game_id * 1000 + room_fee)
        g["all_card_grids"] = {i + 1: cards[i] for i in range(config.TOTAL_CARDS)}
    return g["game_id"]


async def start_countdown(app: Application, room_fee: int) -> None:
    g = GAMES[room_fee]
    if g["status"] == "countdown" and g["countdown_task"]:
        return  # Already counting
    g["status"] = "countdown"
    g["countdown_task"] = asyncio.create_task(
        _countdown_loop(app, room_fee)
    )


async def _countdown_loop(app: Application, room_fee: int) -> None:
    g = GAMES[room_fee]
    for remaining in range(config.COUNTDOWN_SECONDS, -1, -1):
        if GAMES[room_fee]["status"] != "countdown":
            return
        GAMES[room_fee]["countdown_remaining"] = remaining

        # Broadcast countdown update every 10 seconds + last 5
        if remaining % 10 == 0 or remaining <= 5:
            await _broadcast_lobby_update(app, room_fee)

        if remaining == 0:
            break
        await asyncio.sleep(1)

    # Time's up
    g = GAMES[room_fee]
    sold = len(g["card_owners"])
    if sold < config.MIN_CARDS_TO_START:
        await _refund_and_reset(app, room_fee)
    else:
        await _begin_game(app, room_fee)


async def _broadcast_lobby_update(app: Application, room_fee: int) -> None:
    g = GAMES[room_fee]
    for tid in list(g["participants"]):
        user = await db.get_user(tid)
        if not user:
            continue
        msg_id = g["game_messages"].get(tid)
        text = card_selection_text(room_fee, tid, user)
        markup = card_selection_markup(room_fee, 0, tid, user)
        if msg_id:
            await safe_edit(app.bot, tid, msg_id, text, markup)


async def _refund_and_reset(app: Application, room_fee: int) -> None:
    g = GAMES[room_fee]
    game_id = g["game_id"]
    refunds = await db.refund_game(game_id)
    for (tid, amount) in refunds:
        user = await db.get_user(tid)
        if user:
            await safe_send(app.bot, tid,
                            t("lobby_refund", user, amount=amount))
    # Reset room
    GAMES[room_fee] = _empty_room()


async def _begin_game(app: Application, room_fee: int) -> None:
    g = GAMES[room_fee]
    await db.set_game_status(g["game_id"], "running")
    g["status"] = "running"
    g["called_numbers"] = []

    # Notify all players
    for tid in list(g["participants"]):
        user = await db.get_user(tid)
        if not user:
            continue
        await safe_send(app.bot, tid, t("game_starting", user))

    g["call_task"] = asyncio.create_task(_call_loop(app, room_fee))


async def _call_loop(app: Application, room_fee: int) -> None:
    """Call numbers 1-75 in random order every CALL_INTERVAL seconds."""
    g = GAMES[room_fee]
    numbers = list(range(1, 76))
    random.shuffle(numbers)

    for num in numbers:
        if GAMES[room_fee]["status"] != "running":
            return

        GAMES[room_fee]["called_numbers"].append(num)
        await db.update_called_numbers(g["game_id"], GAMES[room_fee]["called_numbers"])

        called_set = set(GAMES[room_fee]["called_numbers"])

        # Auto-win check
        winners = _find_winners(room_fee, called_set)
        if winners:
            await _finish_game(app, room_fee, winners)
            return

        # Broadcast
        await _broadcast_game_update(app, room_fee, num)
        await asyncio.sleep(config.CALL_INTERVAL_SECONDS)

    # All 75 numbers called with no winner → refund
    await _finish_game(app, room_fee, [])


def _find_winners(room_fee: int, called: set[int]) -> list[tuple[int, int, str]]:
    """
    Returns list of (telegram_id, card_number, win_type) for all winning cards.
    Only checks auto-win users (manual wins are handled by claim_bingo handler).
    Actually for auto-win: checks ALL participants' cards continuously.
    """
    g = GAMES[room_fee]
    winners = []
    for tid in g["auto_win_users"]:
        my_cards = g["user_cards"].get(tid, [])
        for card_num in my_cards:
            grid = g["all_card_grids"].get(card_num)
            if not grid:
                continue
            won, win_type = check_win(grid, called)
            if won:
                winners.append((tid, card_num, win_type))
    return winners


async def _finish_game(
    app: Application,
    room_fee: int,
    winners: list[tuple[int, int, str]],
) -> None:
    g = GAMES[room_fee]
    if g["status"] == "finished":
        return
    g["status"] = "finished"

    game_id = g["game_id"]
    total_pool = g["prize_pool"]
    house_cut = round(total_pool * config.HOUSE_COMMISSION, 2)
    prize_pool_net = round(total_pool - house_cut, 2)

    if not winners:
        # No one won → refund
        refunds = await db.refund_game(game_id)
        for (tid, amount) in refunds:
            user = await db.get_user(tid)
            if user:
                await safe_send(app.bot, tid, t("no_winner_refund", user))
        GAMES[room_fee] = _empty_room()
        asyncio.create_task(_schedule_new_lobby(app, room_fee, 10))
        return

    # Multiple winners split the pot
    winner_tids = list({w[0] for w in winners})
    prize_each = round(prize_pool_net / len(winner_tids), 2)

    await db.finish_game(game_id, winner_tids, prize_each, house_cut)
    for (wid, card_num, win_type) in winners:
        await db.mark_card_winner(game_id, card_num, win_type)

    win_type_label_key = "win_type_line" if winners[0][2] == "line" else "win_type_corners"

    # Notify all players
    for tid in list(g["participants"]):
        user = await db.get_user(tid)
        if not user:
            continue
        if tid in winner_tids:
            # This player won
            my_winning = [w for w in winners if w[0] == tid]
            card_num = my_winning[0][1]
            await safe_send(app.bot, tid,
                            t("you_won", user,
                              card=card_num,
                              win_type=get_text(win_type_label_key, lang(user)),
                              prize=prize_each),
                            markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(
                                    get_text("btn_play_again", lang(user)),
                                    callback_data="rooms",
                                )
                            ]]))
        else:
            winner_user = await db.get_user(winner_tids[0])
            wname = mask_name(
                winner_user.get("first_name", "") if winner_user else "",
                winner_user.get("username", "") if winner_user else "",
            )
            my_win_card = next((w[1] for w in winners if w[0] == winner_tids[0]), 0)
            await safe_send(app.bot, tid,
                            t("someone_won", user,
                              winner=wname,
                              card=my_win_card,
                              win_type=get_text(win_type_label_key, lang(user)),
                              prize=prize_each),
                            markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(
                                    get_text("btn_play_again", lang(user)),
                                    callback_data="rooms",
                                )
                            ]]))

    GAMES[room_fee] = _empty_room()
    asyncio.create_task(_schedule_new_lobby(app, room_fee, 10))


async def _schedule_new_lobby(app: Application, room_fee: int, delay: int) -> None:
    await asyncio.sleep(delay)
    await ensure_game_for_room(app, room_fee)


async def _broadcast_game_update(app: Application, room_fee: int, new_num: int) -> None:
    g = GAMES[room_fee]
    for tid in list(g["participants"]):
        user = await db.get_user(tid)
        if not user:
            continue
        text = game_screen_text(room_fee, user)
        markup = game_screen_markup(room_fee, tid, user)
        msg_id = g["game_messages"].get(tid)
        if msg_id:
            await safe_edit(app.bot, tid, msg_id, text, markup)
        else:
            new_id = await safe_send(app.bot, tid, text, markup)
            if new_id:
                g["game_messages"][tid] = new_id


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_or_create_user(tg.id, tg.username or "", tg.first_name or "")

    # Handle referral: /start REF_CODE
    if ctx.args and not user.get("referred_by"):
        ref_code = ctx.args[0]
        referrer = await _find_user_by_ref(ref_code)
        if referrer and referrer["telegram_id"] != tg.id:
            await db.set_referred_by(tg.id, referrer["telegram_id"])
            # Notify referrer
            ref_user = await db.get_user(referrer["telegram_id"])
            if ref_user:
                await safe_send(
                    ctx.bot, referrer["telegram_id"],
                    t("referral_bonus_received", ref_user, bonus=config.REFERRAL_BONUS)
                )

    if not user.get("phone"):
        await update.message.reply_text(
            t("ask_phone", user),
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Share Phone", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True,
            )
        )
        return PHONE_INPUT

    # Refresh user after possible referral bonus
    user = await db.get_user(tg.id)
    await update.message.reply_text(
        t("main_menu", user, balance=round(user["balance"], 2)),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_markup(user),
    )
    return ConversationHandler.END


async def _find_user_by_ref(code: str):
    return await db.find_user_by_ref_code(code)


async def handle_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    contact = update.message.contact
    tg = update.effective_user
    if contact.user_id != tg.id:
        user = await db.get_user(tg.id)
        await update.message.reply_text(t("invalid_phone", user or {"language": "en"}))
        return PHONE_INPUT

    phone = contact.phone_number.replace("+251", "0").replace("+", "")
    if not phone.startswith("09") or len(phone) != 10:
        phone = "0" + phone[-9:]
    user = await db.get_user(tg.id) or {}
    await db.set_phone(tg.id, phone)
    user = await db.get_user(tg.id)
    await update.message.reply_text(
        t("phone_saved", user),
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        t("main_menu", user, balance=round(user["balance"], 2)),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_markup(user),
    )
    return ConversationHandler.END


async def handle_plain_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    tg = update.effective_user
    user = await db.get_user(tg.id) or {"language": "en"}

    # Validate Ethiopian phone
    digits = text.replace("-", "").replace(" ", "")
    if not (digits.startswith("09") and len(digits) == 10 and digits.isdigit()):
        await update.message.reply_text(t("invalid_phone", user))
        return PHONE_INPUT

    await db.set_phone(tg.id, digits)
    user = await db.get_user(tg.id)
    await update.message.reply_text(t("phone_saved", user), reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(
        t("main_menu", user, balance=round(user["balance"], 2)),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_markup(user),
    )
    return ConversationHandler.END


# ── Callback router ────────────────────────────────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data
    tg = update.effective_user
    user = await db.get_user(tg.id)
    if not user:
        return

    if data == "noop":
        return
    elif data == "main_menu":
        user = await db.get_user(tg.id)
        await q.edit_message_text(
            t("main_menu", user, balance=round(user["balance"], 2)),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_markup(user),
        )
    elif data == "games":
        await q.edit_message_text(
            t("games_menu", user),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Bingo", callback_data="rooms")],
                [InlineKeyboardButton("🔒 Slot (Coming Soon)", callback_data="noop")],
                [InlineKeyboardButton(get_text("btn_back", lang(user)), callback_data="main_menu")],
            ]),
        )
    elif data == "rooms":
        await q.edit_message_text(
            t("room_menu", user),
            parse_mode=ParseMode.HTML,
            reply_markup=rooms_markup(user),
        )
    elif data.startswith("room:"):
        room_fee = int(data.split(":")[1])
        await _show_card_selection(q, tg.id, user, room_fee, page=0, ctx=ctx)
    elif data.startswith("card_page:"):
        _, room_fee_s, page_s = data.split(":")
        room_fee, page = int(room_fee_s), int(page_s)
        await _refresh_card_selection(q, tg.id, user, room_fee, page)
    elif data.startswith("card_toggle:"):
        _, room_fee_s, card_num_s, page_s = data.split(":")
        room_fee, card_num, page = int(room_fee_s), int(card_num_s), int(page_s)
        await _toggle_card(q, tg.id, user, room_fee, card_num, page)
    elif data.startswith("rand_card:"):
        parts = data.split(":")
        room_fee, page, n = int(parts[1]), int(parts[2]), int(parts[3])
        await _pick_random_cards(q, tg.id, user, room_fee, page, n)
    elif data.startswith("buy_cards:"):
        room_fee = int(data.split(":")[1])
        await _buy_cards(q, tg.id, user, room_fee, ctx.application)
    elif data.startswith("auto_win:"):
        room_fee = int(data.split(":")[1])
        _toggle_auto_win(tg.id, room_fee)
        g = GAMES.get(room_fee)
        if g:
            text = game_screen_text(room_fee, user)
            markup = game_screen_markup(room_fee, tg.id, user)
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    elif data.startswith("check_win:"):
        room_fee = int(data.split(":")[1])
        await _handle_check(q, tg.id, user, room_fee)
    elif data.startswith("claim_bingo:"):
        room_fee = int(data.split(":")[1])
        await _handle_bingo_claim(q, tg.id, user, room_fee, ctx.application)
    elif data == "balance":
        user = await db.get_user(tg.id)
        await q.edit_message_text(
            t("balance_msg", user, balance=round(user["balance"], 2)),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(get_text("btn_back", lang(user)), callback_data="main_menu")
            ]]),
        )
    elif data == "profile":
        await _show_profile(q, tg.id, user)
    elif data == "transactions":
        await _show_transactions(q, tg.id, user)
    elif data == "referral":
        await _show_referral(q, tg.id, user)
    elif data == "toggle_lang":
        new_lang = "am" if lang(user) == "en" else "en"
        await db.set_language(tg.id, new_lang)
        user = await db.get_user(tg.id)
        await q.edit_message_text(
            t("main_menu", user, balance=round(user["balance"], 2)),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_markup(user),
        )


# ── Card selection sub-handlers ───────────────────────────────────────────────

async def _show_card_selection(q, user_tid: int, user: dict, room_fee: int, page: int, ctx) -> None:
    await ensure_game_for_room(ctx.application, room_fee)
    g = GAMES[room_fee]
    if g["status"] == "running":
        # Game already in progress — show game screen
        if user_tid in g["participants"]:
            text = game_screen_text(room_fee, user)
            markup = game_screen_markup(room_fee, user_tid, user)
            msg = await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            g["game_messages"][user_tid] = msg.message_id
        else:
            await q.answer("Game already running. Wait for next round.", show_alert=True)
        return

    text = card_selection_text(room_fee, user_tid, user)
    markup = card_selection_markup(room_fee, page, user_tid, user)
    await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def _refresh_card_selection(q, user_tid: int, user: dict, room_fee: int, page: int) -> None:
    text = card_selection_text(room_fee, user_tid, user)
    markup = card_selection_markup(room_fee, page, user_tid, user)
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except BadRequest:
        pass


async def _toggle_card(q, user_tid: int, user: dict, room_fee: int, card_num: int, page: int) -> None:
    g = GAMES[room_fee]
    if g["status"] == "running":
        await q.answer("Game started! No more purchases.", show_alert=True)
        return

    my_cards = g["user_cards"].setdefault(user_tid, [])
    owner = g["card_owners"].get(card_num)

    if owner is not None and owner != user_tid:
        await q.answer("Card already taken!", show_alert=True)
        return

    if card_num in my_cards:
        # Deselect
        my_cards.remove(card_num)
    else:
        # Select
        if len(my_cards) >= config.MAX_CARDS_PER_PLAYER:
            await q.answer(f"Max {config.MAX_CARDS_PER_PLAYER} cards per game!", show_alert=True)
            return
        my_cards.append(card_num)
        g["card_owners"][card_num] = user_tid

    # Remove ownership if deselected
    if card_num not in my_cards and g["card_owners"].get(card_num) == user_tid:
        del g["card_owners"][card_num]

    await _refresh_card_selection(q, user_tid, user, room_fee, page)


async def _pick_random_cards(q, user_tid: int, user: dict, room_fee: int, page: int, n: int) -> None:
    g = GAMES[room_fee]
    my_cards = g["user_cards"].setdefault(user_tid, [])
    can_pick = config.MAX_CARDS_PER_PLAYER - len(my_cards)
    if can_pick <= 0:
        await q.answer(f"Max {config.MAX_CARDS_PER_PLAYER} cards reached!", show_alert=True)
        return
    n = min(n, can_pick)
    available = [i for i in range(1, config.TOTAL_CARDS + 1) if i not in g["card_owners"]]
    picks = random.sample(available, min(n, len(available)))
    for card_num in picks:
        my_cards.append(card_num)
        g["card_owners"][card_num] = user_tid
    await _refresh_card_selection(q, user_tid, user, room_fee, page)


async def _buy_cards(q, user_tid: int, user: dict, room_fee: int, app: Application) -> None:
    g = GAMES[room_fee]
    if g["status"] == "running":
        await q.answer("Game already started!", show_alert=True)
        return

    my_card_nums = g["user_cards"].get(user_tid, [])
    if not my_card_nums:
        await q.answer(get_text("no_cards_selected", lang(user)), show_alert=True)
        return

    total_cost = len(my_card_nums) * room_fee
    if user["balance"] < total_cost - 0.001:
        await q.answer(
            get_text("insufficient_balance", lang(user),
                     need=total_cost, have=round(user["balance"], 2)),
            show_alert=True
        )
        return

    game_id = await ensure_game_for_room(app, room_fee)

    # Atomic purchase — deduct balance then write cards
    ok, new_bal = await db.deduct_balance(user_tid, total_cost, "card_buy",
                                          f"room:{room_fee} cards:{my_card_nums}")
    if not ok:
        await q.answer(
            get_text("insufficient_balance", lang(user),
                     need=total_cost, have=round(user["balance"], 2)),
            show_alert=True
        )
        return

    failed_cards = []
    for card_num in list(my_card_nums):
        grid = g["all_card_grids"].get(card_num)
        success = await db.add_game_card(game_id, user_tid, card_num, grid)
        if not success:
            # Someone else grabbed it — remove from selection
            my_card_nums.remove(card_num)
            if g["card_owners"].get(card_num) == user_tid:
                del g["card_owners"][card_num]
            failed_cards.append(card_num)

    # Refund for failed cards
    if failed_cards:
        refund = len(failed_cards) * room_fee
        await db.add_balance(user_tid, refund, "refund", note="card_taken")

    g["participants"].add(user_tid)
    g["prize_pool"] = len(g["card_owners"]) * room_fee
    await db.update_game_pool(game_id, g["prize_pool"])
    g["last_buyer_name"] = mask_name(user.get("first_name", ""), user.get("username", ""))

    user = await db.get_user(user_tid)

    # Start countdown if threshold met
    sold = len(g["card_owners"])
    if sold >= config.MIN_CARDS_TO_START and g["status"] == "lobby":
        await start_countdown(app, room_fee)

    # Show waiting screen
    status_text = t("countdown_started", user, sec=g["countdown_remaining"], sold=sold) \
        if g["status"] == "countdown" \
        else t("waiting_start", user, sold=sold)
    msg = await q.edit_message_text(status_text, parse_mode=ParseMode.HTML)
    g["game_messages"][user_tid] = msg.message_id


# ── Win claim handlers ─────────────────────────────────────────────────────────

def _toggle_auto_win(user_tid: int, room_fee: int) -> None:
    g = GAMES.get(room_fee)
    if not g:
        return
    if user_tid in g["auto_win_users"]:
        g["auto_win_users"].discard(user_tid)
    else:
        g["auto_win_users"].add(user_tid)


async def _handle_check(q, user_tid: int, user: dict, room_fee: int) -> None:
    g = GAMES.get(room_fee)
    if not g or g["status"] != "running":
        await q.answer(get_text("not_in_game", lang(user)), show_alert=True)
        return
    called_set = set(g["called_numbers"])
    my_cards = g["user_cards"].get(user_tid, [])
    wins = []
    for card_num in my_cards:
        grid = g["all_card_grids"].get(card_num)
        if grid:
            won, wt = check_win(grid, called_set)
            if won:
                wins.append((card_num, wt))
    if wins:
        card_txt = "\n".join(
            render_card_text(g["all_card_grids"][cn], called_set, cn)
            for (cn, _) in wins
        )
        await q.answer(f"You have a winning card! Tap BINGO! 🎉", show_alert=True)
    else:
        await q.answer("No winning pattern yet. Keep playing!", show_alert=False)


async def _handle_bingo_claim(q, user_tid: int, user: dict, room_fee: int, app: Application) -> None:
    g = GAMES.get(room_fee)
    if not g or g["status"] != "running":
        await q.answer(get_text("not_in_game", lang(user)), show_alert=True)
        return
    called_set = set(g["called_numbers"])
    my_cards = g["user_cards"].get(user_tid, [])
    winners = []
    for card_num in my_cards:
        grid = g["all_card_grids"].get(card_num)
        if grid:
            won, wt = check_win(grid, called_set)
            if won:
                winners.append((user_tid, card_num, wt))
    if winners:
        await _finish_game(app, room_fee, winners)
    else:
        await q.answer(get_text("false_bingo", lang(user)), show_alert=True)


# ── Profile / Transactions / Referral ─────────────────────────────────────────

async def _show_profile(q, user_tid: int, user: dict) -> None:
    ref_count = await db.get_user_referral_count(user_tid)
    text = t("profile", user,
             tid=user_tid,
             username=user.get("username") or "—",
             phone=user.get("phone") or "—",
             balance=round(user["balance"], 2),
             games=user.get("games_played", 0),
             won=round(user.get("total_won", 0), 2),
             ref_code=user.get("referral_code", "—"),
             ref_count=ref_count)
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(get_text("btn_back", lang(user)), callback_data="main_menu")
        ]]),
    )


async def _show_transactions(q, user_tid: int, user: dict) -> None:
    txs = await db.get_user_transactions(user_tid, 10)
    L = lang(user)
    emoji_map = {
        "deposit": "📥", "withdraw": "📤", "transfer_out": "➡️",
        "transfer_in": "⬅️", "card_buy": "🎯", "win": "🏆",
        "refund": "🔄", "referral": "🎁",
    }
    lines = [get_text("transactions_header", L)]
    for tx in txs:
        emoji = emoji_map.get(tx["type"], "💰")
        date_str = datetime.fromtimestamp(tx["created_at"]).strftime("%m/%d %H:%M")
        lines.append(get_text("tx_row", L,
                               emoji=emoji, type=tx["type"],
                               amount=abs(round(tx["amount"], 2)), date=date_str))
    if len(lines) == 1:
        lines.append(get_text("no_transactions", L))
    await q.edit_message_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(get_text("btn_back", L), callback_data="main_menu")
        ]]),
    )


async def _show_referral(q, user_tid: int, user: dict) -> None:
    ref_count = await db.get_user_referral_count(user_tid)
    text = t("referral_info", user,
             bonus=config.REFERRAL_BONUS,
             bot=config.BOT_USERNAME,
             code=user.get("referral_code", ""),
             count=ref_count)
    await q.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(get_text("btn_back", lang(user)), callback_data="main_menu")
        ]]),
    )


# ── Deposit ConversationHandler ────────────────────────────────────────────────

async def deposit_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    tg = update.effective_user
    user = await db.get_user(tg.id)
    amounts_row = [InlineKeyboardButton(str(a), callback_data=f"dep_amt:{a}")
                   for a in [50, 100, 200, 500]]
    markup = InlineKeyboardMarkup([
        amounts_row,
        [InlineKeyboardButton(get_text("btn_back", lang(user)), callback_data="main_menu")],
    ])
    await q.edit_message_text(
        t("deposit_choose_amount", user, min=config.MIN_DEPOSIT),
        parse_mode=ParseMode.HTML, reply_markup=markup,
    )
    return DEPOSIT_AMOUNT


async def deposit_amount_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    amount = float(q.data.split(":")[1])
    return await _send_deposit_instructions(update, ctx, amount)


async def deposit_amount_typed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    text = (update.message.text or "").strip()
    try:
        amount = float(text)
        if amount < config.MIN_DEPOSIT:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            t("invalid_amount", user, min=config.MIN_DEPOSIT), parse_mode=ParseMode.HTML
        )
        return DEPOSIT_AMOUNT
    return await _send_deposit_instructions(update, ctx, amount)


async def _send_deposit_instructions(update, ctx, amount: float) -> int:
    tg = update.effective_user if update.effective_user else update.callback_query.from_user
    user = await db.get_user(tg.id)
    acct = await db.get_active_deposit_account()
    if not acct:
        await (update.message or update.callback_query).reply_text("No deposit accounts configured. Contact support.")
        return ConversationHandler.END

    ctx.user_data["deposit_amount"] = amount
    ctx.user_data["deposit_account_id"] = acct["id"]

    text = t("deposit_instructions", user,
             amount=amount, account_phone=acct["phone"], account_name=acct["name"])
    send = update.message.reply_text if update.message else update.callback_query.message.reply_text
    await send(text, parse_mode=ParseMode.HTML)
    return DEPOSIT_SMS


async def deposit_sms_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    sms_text = (update.message.text or "").strip()

    await update.message.reply_text(t("deposit_verifying", user))

    parsed = parse_telebirr_sms(sms_text)
    if not parsed:
        await update.message.reply_text(t("deposit_failed_parse", user))
        return DEPOSIT_SMS

    if not verify_recipient(parsed, config.ACCEPTED_RECIPIENT_NAMES, config.ACCEPTED_PHONE_LAST4):
        await update.message.reply_text(t("deposit_failed_recipient", user))
        return DEPOSIT_SMS

    req_amount = ctx.user_data.get("deposit_amount", 0)
    if not verify_amount(parsed, req_amount):
        await update.message.reply_text(
            t("deposit_failed_amount", user, sms_amount=parsed.amount, req_amount=req_amount)
        )
        return DEPOSIT_SMS

    if await db.is_ref_used(parsed.reference):
        await update.message.reply_text(t("deposit_duplicate_ref", user))
        return DEPOSIT_SMS

    await db.mark_ref_used(parsed.reference)
    acct_id = ctx.user_data.get("deposit_account_id")
    if acct_id:
        await db.increment_account_deposits(acct_id)

    new_bal = await db.add_balance(tg.id, parsed.amount, "deposit", parsed.reference)
    await update.message.reply_text(
        t("deposit_success", user, amount=parsed.amount, balance=round(new_bal, 2)),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def deposit_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    (update.message or update.callback_query).reply_text(t("deposit_cancelled", user))
    return ConversationHandler.END


# ── Withdraw ConversationHandler ───────────────────────────────────────────────

async def withdraw_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    tg = update.effective_user
    user = await db.get_user(tg.id)
    if not user.get("phone"):
        await q.edit_message_text(t("withdraw_no_phone", user), parse_mode=ParseMode.HTML,
                                   reply_markup=InlineKeyboardMarkup([[
                                       InlineKeyboardButton(get_text("btn_back", lang(user)), callback_data="main_menu")
                                   ]]))
        return ConversationHandler.END
    await q.edit_message_text(
        t("withdraw_prompt", user,
          phone=user["phone"],
          balance=round(user["balance"], 2),
          min=config.MIN_WITHDRAWAL),
        parse_mode=ParseMode.HTML,
    )
    return WITHDRAW_AMOUNT


async def withdraw_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    text = (update.message.text or "").strip()
    try:
        amount = float(text)
        if amount < config.MIN_WITHDRAWAL:
            raise ValueError
    except ValueError:
        await update.message.reply_text(t("invalid_amount", user, min=config.MIN_WITHDRAWAL))
        return WITHDRAW_AMOUNT

    if user["balance"] < amount:
        await update.message.reply_text(
            t("insufficient_balance", user, need=amount, have=round(user["balance"], 2))
        )
        return WITHDRAW_AMOUNT

    wd_id = await db.create_withdrawal(tg.id, amount, user["phone"])
    await update.message.reply_text(t("withdraw_requested", user, amount=amount), parse_mode=ParseMode.HTML)

    # Notify admin
    await safe_send(ctx.bot, config.ADMIN_ID,
                    f"💸 <b>New Withdrawal Request</b>\n"
                    f"#{wd_id} | @{user.get('username') or 'N/A'} | "
                    f"{amount} ETB → {user['phone']}",
                    markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(f"✅ Approve #{wd_id}", callback_data=f"wd_approve:{wd_id}"),
                        InlineKeyboardButton(f"❌ Reject #{wd_id}", callback_data=f"wd_reject:{wd_id}"),
                    ]]))
    return ConversationHandler.END


# ── Transfer ConversationHandler ───────────────────────────────────────────────

async def transfer_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    tg = update.effective_user
    user = await db.get_user(tg.id)
    await q.edit_message_text(t("transfer_prompt_user", user), parse_mode=ParseMode.HTML)
    return TRANSFER_USER


async def transfer_user_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    username = (update.message.text or "").strip().lstrip("@")
    recipient = await db.get_user_by_username(username)
    if not recipient:
        await update.message.reply_text(t("transfer_user_not_found", user, username=username))
        return TRANSFER_USER
    if recipient["telegram_id"] == tg.id:
        await update.message.reply_text(t("transfer_self", user))
        return TRANSFER_USER
    ctx.user_data["transfer_to"] = recipient
    await update.message.reply_text(
        t("transfer_prompt_amount", user,
          min=config.MIN_TRANSFER, balance=round(user["balance"], 2)),
        parse_mode=ParseMode.HTML,
    )
    return TRANSFER_AMOUNT


async def transfer_amount_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = await db.get_user(tg.id)
    text = (update.message.text or "").strip()
    try:
        amount = float(text)
        if amount < config.MIN_TRANSFER:
            raise ValueError
    except ValueError:
        await update.message.reply_text(t("invalid_amount", user, min=config.MIN_TRANSFER))
        return TRANSFER_AMOUNT

    # Cooldown check
    elapsed = time.time() - (user.get("last_transfer_at") or 0)
    if elapsed < config.TRANSFER_COOLDOWN_SECONDS:
        mins = int((config.TRANSFER_COOLDOWN_SECONDS - elapsed) / 60) + 1
        await update.message.reply_text(t("transfer_cooldown", user, mins=mins))
        return ConversationHandler.END

    to = ctx.user_data.get("transfer_to")
    if not to:
        return ConversationHandler.END

    ok, err = await db.transfer_balance(tg.id, to["telegram_id"], amount)
    if not ok:
        await update.message.reply_text(t("insufficient_balance", user,
                                          need=amount, have=round(user["balance"], 2)))
        return ConversationHandler.END

    user = await db.get_user(tg.id)
    await update.message.reply_text(
        t("transfer_success", user, amount=amount,
          to=to.get("username") or to["telegram_id"],
          balance=round(user["balance"], 2)),
        parse_mode=ParseMode.HTML,
    )
    # Notify recipient
    to_user = await db.get_user(to["telegram_id"])
    if to_user:
        await safe_send(ctx.bot, to["telegram_id"],
                        t("transfer_received", to_user, amount=amount,
                          from_user=user.get("username") or tg.id))
    return ConversationHandler.END


# ── Admin handlers ─────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tg = update.effective_user
    if tg.id != config.ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    stats = await db.get_stats()
    text = (f"⚙️ <b>Admin Panel</b>\n\n"
            f"👥 Users: {stats['users']}\n"
            f"🎮 Games: {stats['games']}\n"
            f"💵 Collected: {stats['collected']} ETB\n"
            f"🏦 Profit: {stats['profit']} ETB\n"
            f"💸 Pending WDs: {stats['pending_wd']}")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Withdrawals", callback_data="admin_wds"),
         InlineKeyboardButton("🏦 Accounts", callback_data="admin_accounts")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    tg = update.effective_user
    if tg.id != config.ADMIN_ID:
        return ConversationHandler.END

    data = q.data
    if data == "admin_stats":
        stats = await db.get_stats()
        await q.edit_message_text(
            f"📊 Users: {stats['users']} | Games: {stats['games']}\n"
            f"Collected: {stats['collected']} ETB | Profit: {stats['profit']} ETB",
            parse_mode=ParseMode.HTML,
        )
    elif data == "admin_wds":
        wds = await db.get_pending_withdrawals()
        if not wds:
            await q.edit_message_text("✅ No pending withdrawals.")
            return ConversationHandler.END
        rows = []
        for wd in wds:
            rows.append([
                InlineKeyboardButton(
                    f"✅ #{wd['id']} {wd['amount']} ETB @{wd.get('username','?')}",
                    callback_data=f"wd_approve:{wd['id']}"
                ),
                InlineKeyboardButton("❌", callback_data=f"wd_reject:{wd['id']}"),
            ])
        await q.edit_message_text("💸 Pending Withdrawals:", reply_markup=InlineKeyboardMarkup(rows))
    elif data.startswith("wd_approve:"):
        wd_id = int(data.split(":")[1])
        wd = await db.approve_withdrawal(wd_id)
        if wd:
            await q.edit_message_text(f"✅ Withdrawal #{wd_id} approved. Send {wd['amount']} ETB → {wd['phone']}")
            notif_user = await db.get_user(wd["telegram_id"])
            if notif_user:
                await safe_send(ctx.bot, wd["telegram_id"],
                                get_text("withdrawal_notify_approved", lang(notif_user), amount=wd["amount"]))
    elif data.startswith("wd_reject:"):
        wd_id = int(data.split(":")[1])
        wd = await db.reject_withdrawal(wd_id)
        if wd:
            await q.edit_message_text(f"❌ Withdrawal #{wd_id} rejected. {wd['amount']} ETB refunded.")
            notif_user = await db.get_user(wd["telegram_id"])
            if notif_user:
                await safe_send(ctx.bot, wd["telegram_id"],
                                get_text("withdrawal_notify_rejected", lang(notif_user), amount=wd["amount"]))
    elif data == "admin_broadcast":
        await q.edit_message_text("📢 Send your broadcast message now (text or photo):")
        return ADMIN_BROADCAST
    elif data == "admin_accounts":
        accts = await db.get_deposit_accounts()
        lines = ["🏦 <b>Deposit Accounts</b>"]
        for a in accts:
            status = "✅" if a["is_active"] else "❌"
            lines.append(f"{status} #{a['id']} {a['name']} | {a['phone']} (deposits: {a['deposit_count']})")
        lines.append("\nSend <code>phone|name</code> to add or <code>remove:ID</code> to remove:")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return ADMIN_ACCOUNTS
    return ConversationHandler.END


async def admin_broadcast_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != config.ADMIN_ID:
        return ConversationHandler.END
    all_tids = await db.get_all_user_tids()
    count = 0
    for tid in all_tids:
        try:
            if update.message.photo:
                await ctx.bot.send_photo(tid, update.message.photo[-1].file_id,
                                          caption=update.message.caption or "")
            else:
                await ctx.bot.send_message(tid, update.message.text or "",
                                            parse_mode=ParseMode.HTML)
            count += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)  # Rate limit
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")
    return ConversationHandler.END


async def admin_accounts_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != config.ADMIN_ID:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if text.startswith("remove:"):
        acct_id = int(text.split(":")[1])
        await db.remove_deposit_account(acct_id)
        await update.message.reply_text(f"✅ Account #{acct_id} deactivated.")
    elif "|" in text:
        parts = text.split("|", 1)
        phone, name = parts[0].strip(), parts[1].strip()
        new_id = await db.add_deposit_account(phone, name)
        await update.message.reply_text(f"✅ Account #{new_id} added: {name} ({phone})")
    else:
        await update.message.reply_text("Invalid format. Use phone|name or remove:ID")
    return ConversationHandler.END


# ── Error handler ──────────────────────────────────────────────────────────────

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception:", exc_info=ctx.error)


# ── Application setup & main ───────────────────────────────────────────────────

def build_app() -> Application:
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # ── Registration conversation ──
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            PHONE_INPUT: [
                MessageHandler(filters.CONTACT, handle_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_phone),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        per_message=False,
    )
    app.add_handler(reg_conv)

    # ── Deposit conversation ──
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
        states={
            DEPOSIT_AMOUNT: [
                CallbackQueryHandler(deposit_amount_selected, pattern=r"^dep_amt:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_typed),
            ],
            DEPOSIT_SMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_sms_received),
            ],
        },
        fallbacks=[CallbackQueryHandler(deposit_cancel, pattern="^main_menu$")],
        per_message=False,
    )
    app.add_handler(deposit_conv)

    # ── Withdraw conversation ──
    wd_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw$")],
        states={
            WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount),
            ],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(wd_conv)

    # ── Transfer conversation ──
    tr_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(transfer_start, pattern="^transfer$")],
        states={
            TRANSFER_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_user_input)],
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount_input)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(tr_conv)

    # ── Admin conversation ──
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^admin_")],
        states={
            ADMIN_BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_broadcast_message)],
            ADMIN_ACCOUNTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_accounts_message)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(admin_conv)

    # ── Admin withdrawal approve/reject (outside conv) ──
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^wd_(approve|reject):"))

    # ── Main callback handler ──
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Admin command ──
    app.add_handler(CommandHandler("admin", cmd_admin))

    app.add_error_handler(error_handler)
    return app


async def main() -> None:
    await db.init_db()
    _init_all_rooms()

    app = build_app()

    # Restore active game state from DB on startup
    for fee in config.ROOM_FEES:
        g_row = await db.get_active_game(fee)
        if g_row:
            GAMES[fee]["game_id"] = g_row["id"]
            GAMES[fee]["status"] = g_row["status"]
            GAMES[fee]["prize_pool"] = g_row["prize_pool"]
            # Reload called numbers
            GAMES[fee]["called_numbers"] = json.loads(g_row["called_numbers"] or "[]")
            # Reload card owners
            GAMES[fee]["card_owners"] = await db.get_card_owners(g_row["id"])
            # Reload card grids
            cards = generate_unique_cards(config.TOTAL_CARDS, seed=g_row["id"] * 1000 + fee)
            GAMES[fee]["all_card_grids"] = {i + 1: cards[i] for i in range(config.TOTAL_CARDS)}
        else:
            await ensure_game_for_room(app, fee)

    logger.info("Habesha Bet Bingo Bot starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
