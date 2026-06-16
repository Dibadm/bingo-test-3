# bot.py
# ============================================
# HABESHA BET - MULTIPLAYER BINGO BOT
# Main Telegram bot file.
#
# Architecture:
#   - 4 permanent rooms (10/20/50/100 ETB), each always has a "waiting"
#     or "running" game row (see database.get_or_create_active_game).
#   - One asyncio task per running game drives the 60s countdown AND
#     the number-calling loop (run_game_lifecycle). The task is started
#     the moment the 2nd card is sold in a room and is tracked in
#     ACTIVE_GAME_TASKS so a 2nd countdown can never be started for the
#     same room while one is already running.
#   - Every player who joins a game gets their OWN message that the
#     lifecycle task edits directly (chat_id + message_id stored via
#     database.upsert_game_player_message), so N players see N
#     independently-updating live game screens from one shared call
#     sequence.
#   - Win checking: corners and line pay identically and split equally
#     among all simultaneous winners (per product decision) - see
#     resolve_round_end().
#
# HOW TO RUN:
#   1. Fill in config.py (BOT_TOKEN, ADMIN_IDS, BOT_USERNAME, etc.)
#   2. pip install -r requirements.txt
#   3. python bot.py
# ============================================

import asyncio
import html
import logging
import os
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.error import BadRequest, Forbidden

import config
import database as db
import bingo
from locales import get_text, get_user_text, STRINGS
from sms_parser import parse_telebirr_sms, verify_recipient, validate_deposit_amount

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# =====================================================================
# IN-MEMORY GAME STATE (per-process; resets on restart)
# =====================================================================

# room_fee -> asyncio.Task running that room's current countdown/game loop.
# Used to guarantee only ONE lifecycle task per room at a time.
ACTIVE_GAME_TASKS = {}

# room_fee -> asyncio.Lock, guards "start a new lifecycle task for this room"
# so two near-simultaneous card purchases can't both spawn a task.
ROOM_LOCKS = {fee: asyncio.Lock() for fee in config.ROOM_FEES}

# game_id -> {user_id: {card_index: win_type}} - populated by the manual
# BINGO button handler (game_bingo_claim) the instant a valid claim is
# pressed. The calling loop in run_game_lifecycle checks this dict after
# every single call (not just its own auto-win check) so a manual press
# is picked up within one CALL_DELAY_SECONDS window even if it happens
# between calls rather than exactly when push_call_and_check_wins runs.
GAME_MANUAL_CLAIMS = {}

# Conversation states
(
    PHONE_COLLECT,
    WITHDRAW_AMOUNT,
    WITHDRAW_PHONE,
    TRANSFER_USERNAME,
    TRANSFER_AMOUNT,
    DEPOSIT_CUSTOM_AMOUNT,
    ADMIN_BROADCAST_WAIT,
    ADMIN_ADD_ACCOUNT_PHONE,
    ADMIN_ADD_ACCOUNT_NAME,
) = range(9)


# =====================================================================
# SMALL HELPERS
# =====================================================================

def lang_of(user_row) -> str:
    return user_row["language"] if user_row and "language" in user_row.keys() else config.DEFAULT_LANGUAGE


def display_name(user) -> str:
    """Telegram User object -> a name to store/display before masking."""
    return user.username or user.first_name or str(user.id)


def safe_amount(text: str):
    """Parse a user-typed amount string. Returns float or None."""
    try:
        value = float(text.strip().replace(",", ""))
        if value <= 0:
            return None
        return round(value, 2)
    except (ValueError, AttributeError):
        return None


async def safe_edit(query, text, reply_markup=None, parse_mode="HTML"):
    """Edit a callback query's message, swallowing the extremely common
    'Message is not modified' BadRequest that fires when the new text/
    markup happens to be identical to what's already shown (this happens
    constantly with live-updating game screens)."""
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning(f"safe_edit BadRequest: {e}")


async def safe_edit_by_id(bot, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    """Same as safe_edit but for editing an arbitrary (chat_id, message_id)
    pair instead of a callback query's own message - needed because the
    game lifecycle loop must push updates to EVERY player's message, not
    just the one who triggered the action."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text,
            parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning(f"safe_edit_by_id BadRequest ({chat_id}/{message_id}): {e}")
    except Forbidden:
        logger.info(f"User {chat_id} blocked the bot - skipping update")


def fmt(amount) -> str:
    """Consistent ETB amount formatting - no trailing .0 noise for whole numbers."""
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.2f}"


# =====================================================================
# KEYBOARDS
# =====================================================================

def main_menu_keyboard(lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text("btn_play_games", lang), callback_data="menu_play")],
        [
            InlineKeyboardButton(get_text("btn_deposit", lang), callback_data="menu_deposit"),
            InlineKeyboardButton(get_text("btn_withdraw", lang), callback_data="menu_withdraw"),
        ],
        [
            InlineKeyboardButton(get_text("btn_transfer", lang), callback_data="menu_transfer"),
            InlineKeyboardButton(get_text("btn_profile", lang), callback_data="menu_profile"),
        ],
        [
            InlineKeyboardButton(get_text("btn_transactions", lang), callback_data="menu_transactions"),
            InlineKeyboardButton(get_text("btn_balance", lang), callback_data="menu_balance"),
        ],
        [
            InlineKeyboardButton(get_text("btn_join_group", lang), url=config.GROUP_LINK),
            InlineKeyboardButton(get_text("btn_contact", lang), url=f"https://t.me/{config.SUPPORT_USERNAME}"),
        ],
        [InlineKeyboardButton(get_text("btn_refer", lang), callback_data="menu_referral")],
        [
            InlineKeyboardButton(get_text("btn_daily_bonus", lang), callback_data="menu_bonus"),
            InlineKeyboardButton(get_text("btn_language", lang), callback_data="menu_language"),
        ],
    ])


def back_keyboard(lang) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_text("btn_back", lang), callback_data="back_main")]])


def games_menu_keyboard(lang) -> InlineKeyboardMarkup:
    bingo_count = sum(len(db.get_game_players(db.get_or_create_active_game(fee)["id"])) for fee in config.ROOM_FEES)
    bingo_label = f"{get_text('btn_bingo', lang)} 🟢{bingo_count}"

    rows = [
        [InlineKeyboardButton(bingo_label, callback_data="games_bingo")],
        [
            InlineKeyboardButton(f"{get_text('btn_ludo', lang)} ({get_text('coming_soon', lang)})", callback_data="noop"),
            InlineKeyboardButton(f"{get_text('btn_cards', lang)} ({get_text('coming_soon', lang)})", callback_data="noop"),
        ],
        [InlineKeyboardButton(f"{get_text('btn_conquer', lang)} ({get_text('coming_soon', lang)})", callback_data="noop")],
        [InlineKeyboardButton(get_text("btn_back", lang), callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(rows)


def rooms_keyboard(lang) -> InlineKeyboardMarkup:
    rows = []
    for fee in config.ROOM_FEES:
        game = db.get_or_create_active_game(fee)
        pool = fmt(game["pool"])
        players = len(db.get_game_players(game["id"]))
        label = get_text("room_btn", lang, fee=fmt(fee), pool=pool, players=players)
        rows.append([InlineKeyboardButton(label, callback_data=f"room_{fee}")])
    rows.append([InlineKeyboardButton(get_text("btn_back", lang), callback_data="menu_play")])
    return InlineKeyboardMarkup(rows)


CARDS_PER_PAGE = 40  # 4 rows x 10 columns


def build_card_page_keyboard(game_id, room_fee, lang, page, selected_indices):
    """Render one page (40 cards) of the 200-card grid as inline buttons.
    selected_indices = the cards THIS user has tapped in the current
    session but not yet purchased (kept in context.user_data, not DB,
    until the START button is pressed)."""
    taken = db.get_taken_cards(game_id)
    total_pages = (config.CARD_POOL_SIZE + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    start = page * CARDS_PER_PAGE
    end = min(start + CARDS_PER_PAGE, config.CARD_POOL_SIZE)

    rows = []
    row = []
    for idx in range(start, end):
        display_num = idx + 1
        if idx in taken:
            text = f"⬛{display_num}"
        elif idx in selected_indices:
            text = f"✅{display_num}"
        else:
            text = str(display_num)
        row.append(InlineKeyboardButton(text, callback_data=f"cardtap_{idx}"))
        if len(row) == 10:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Pager row
    pager = []
    if page > 0:
        pager.append(InlineKeyboardButton("⬅️", callback_data=f"cardpage_{page-1}"))
    pager.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        pager.append(InlineKeyboardButton("➡️", callback_data=f"cardpage_{page+1}"))
    rows.append(pager)

    # Random pick + start row
    rows.append([
        InlineKeyboardButton(get_text("btn_random_x1", lang), callback_data="random_1"),
        InlineKeyboardButton(get_text("btn_random_x2", lang), callback_data="random_2"),
    ])

    cost = len(selected_indices) * room_fee
    start_label = get_text("btn_start_cost", lang, cost=fmt(cost)) if selected_indices else get_text("btn_start_game", lang)
    rows.append([InlineKeyboardButton(start_label, callback_data="confirm_purchase")])
    rows.append([InlineKeyboardButton(get_text("btn_back", lang), callback_data="menu_play")])

    return InlineKeyboardMarkup(rows)


def active_game_keyboard(lang, auto_win_on: bool, marked_count: int = 0, total_called: int = 0) -> InlineKeyboardMarkup:
    auto_label = get_text("auto_win_on", lang) if auto_win_on else get_text("auto_win_off", lang)
    check_label = get_text("btn_check_all", lang, n=marked_count, total=total_called)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(check_label, callback_data="game_check")],
        [
            InlineKeyboardButton(auto_label, callback_data="game_toggle_auto"),
            InlineKeyboardButton(get_text("btn_bingo_claim", lang), callback_data="game_bingo_claim"),
        ],
    ])


def play_again_keyboard(lang, room_fee) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text("btn_play_again", lang), callback_data=f"room_{room_fee}")],
        [InlineKeyboardButton(get_text("btn_back", lang), callback_data="back_main")],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])


def deposit_amount_keyboard(lang) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for amt in config.DEPOSIT_QUICK_AMOUNTS:
        row.append(InlineKeyboardButton(f"{amt} ETB", callback_data=f"depamt_{amt}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(get_text("btn_custom_amount", lang), callback_data="depamt_custom")])
    rows.append([InlineKeyboardButton(get_text("btn_back", lang), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def withdraw_approval_keyboard(withdrawal_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"wdapprove_{withdrawal_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"wdreject_{withdrawal_id}"),
    ]])


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
        [InlineKeyboardButton("💸 Withdrawals", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🏦 Deposit Accounts", callback_data="admin_accounts")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🏛️ House Wallet", callback_data="admin_house")],
    ])


# =====================================================================
# /start  +  PHONE COLLECTION  (referral deep links: t.me/bot?start=ref123456)
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = db.get_user(user.id)
    is_new = existing is None

    referred_by = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref"):
            try:
                ref_id = int(arg[3:])
                if ref_id != user.id and db.get_user(ref_id) is not None:
                    referred_by = ref_id
            except ValueError:
                pass

    db_user = db.get_or_create_user(user.id, display_name(user), referred_by=referred_by)
    lang = lang_of(db_user)

    if is_new or not db_user["phone"]:
        # Must collect phone before anything else (needed for withdrawals)
        contact_button = KeyboardButton(get_text("share_phone_button", lang), request_contact=True)
        keyboard = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            get_text("welcome_new", lang), parse_mode="HTML", reply_markup=keyboard
        )
        return PHONE_COLLECT

    await show_main_menu(update, context, db_user)
    return ConversationHandler.END


async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    contact = update.message.contact

    if contact is None or contact.user_id != user.id:
        # Reject contacts shared on behalf of someone else
        db_user = db.get_user(user.id)
        lang = lang_of(db_user)
        await update.message.reply_text(get_text("share_phone_button", lang))
        return PHONE_COLLECT

    db.set_user_phone(user.id, contact.phone_number)
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)

    prefix = ""
    if db_user["referred_by"] is not None and config.SIGNUP_BONUS > 0:
        db.adjust_balance(user.id, config.SIGNUP_BONUS)
        db.record_transaction(user.id, "signup_bonus", config.SIGNUP_BONUS, status="completed")
        prefix = get_text("signup_bonus_received", lang, amount=fmt(config.SIGNUP_BONUS))

    await update.message.reply_text(
        prefix + get_text("phone_saved", lang), parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
    )

    db_user = db.get_user(user.id)
    await show_main_menu(update, context, db_user)
    return ConversationHandler.END


async def show_main_menu(update_or_query, context, db_user, edit=False):
    lang = lang_of(db_user)
    text = get_text(
        "main_menu_text", lang,
        username=html.escape(db_user["username"] or str(db_user["user_id"])),
        balance=fmt(db_user["balance"]),
    )
    markup = main_menu_keyboard(lang)

    if edit:
        await safe_edit(update_or_query, text, reply_markup=markup)
    else:
        await update_or_query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


# =====================================================================
# MAIN MENU CALLBACKS
# =====================================================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db_user = db.get_user(user.id)
    if db_user is None:
        await query.answer(get_text("error_generic", config.DEFAULT_LANGUAGE), show_alert=True)
        return
    lang = lang_of(db_user)
    data = query.data

    if data == "back_main":
        db_user = db.get_user(user.id)  # refresh balance
        await show_main_menu(query, context, db_user, edit=True)

    elif data == "menu_balance":
        await safe_edit(
            query,
            get_text("main_menu_text", lang, username=html.escape(db_user["username"] or ""), balance=fmt(db_user["balance"])),
            reply_markup=back_keyboard(lang),
        )

    elif data == "menu_profile":
        joined_date = db_user["created_at"][:10] if db_user["created_at"] else "-"
        text = get_text(
            "profile_text", lang,
            username=html.escape(db_user["username"] or ""),
            user_id=db_user["user_id"],
            phone=db_user["phone"] or "-",
            balance=fmt(db_user["balance"]),
            referrals=db.count_referrals(user.id),
            joined=joined_date,
        )
        await safe_edit(query, text, reply_markup=back_keyboard(lang))

    elif data == "menu_transactions":
        await show_transactions(query, db_user)

    elif data == "menu_bonus":
        await handle_daily_bonus(query, db_user)

    elif data == "menu_referral":
        await handle_referral_info(query, db_user)

    elif data == "menu_language":
        await safe_edit(query, "🌐 Language / ቋንቋ", reply_markup=language_keyboard())

    elif data == "lang_en":
        db.set_user_language(user.id, "en")
        await query.answer(get_text("language_switched_en", "en"))
        await show_main_menu(query, context, db.get_user(user.id), edit=True)

    elif data == "lang_am":
        db.set_user_language(user.id, "am")
        await query.answer(get_text("language_switched_am", "am"))
        await show_main_menu(query, context, db.get_user(user.id), edit=True)

    elif data == "menu_play":
        await safe_edit(query, get_text("games_menu_text", lang), reply_markup=games_menu_keyboard(lang))

    elif data == "menu_deposit":
        await menu_deposit_entry(query, context, db_user)

    elif data == "games_bingo":
        await safe_edit(query, get_text("bingo_rooms_text", lang), reply_markup=rooms_keyboard(lang))

    elif data == "noop":
        pass  # disabled / coming-soon buttons, or pager page-count label

    elif data.startswith("room_"):
        fee = float(data.split("_", 1)[1])
        await enter_room(query, context, db_user, fee)

    elif data.startswith("cardpage_"):
        page = int(data.split("_", 1)[1])
        await show_card_page(query, context, db_user, page)

    elif data.startswith("cardtap_"):
        idx = int(data.split("_", 1)[1])
        await toggle_card_selection(query, context, db_user, idx)

    elif data.startswith("random_"):
        count = int(data.split("_", 1)[1])
        await random_pick(query, context, db_user, count)

    elif data == "confirm_purchase":
        await confirm_purchase(query, context, db_user)

    elif data == "game_check":
        await game_check_all(query, context, db_user)

    elif data == "game_toggle_auto":
        await game_toggle_auto(query, context, db_user)

    elif data == "game_bingo_claim":
        await game_bingo_claim(query, context, db_user)

    elif data.startswith("depamt_"):
        await deposit_amount_chosen(query, context, db_user, data)

    elif data.startswith("wdapprove_"):
        await admin_approve_withdrawal(query, context, int(data.split("_", 1)[1]))

    elif data.startswith("wdreject_"):
        await admin_reject_withdrawal(query, context, int(data.split("_", 1)[1]))

    elif data.startswith("admin_"):
        await admin_callback(query, context, db_user, data)


TX_ICONS = {
    "deposit": "💳", "withdraw": "💸", "withdraw_refund": "↩️", "transfer_in": "📥", "transfer_out": "📤",
    "bingo_bet": "🎲", "bingo_win": "🏆", "bingo_refund": "↩️",
    "referral_bonus": "👥", "signup_bonus": "🎁", "daily_bonus": "🎁",
    "house_commission": "🏛️",
}


async def show_transactions(query, db_user):
    lang = lang_of(db_user)
    rows = db.get_user_transactions(db_user["user_id"], limit=10)

    if not rows:
        await safe_edit(query, get_text("no_transactions", lang), reply_markup=back_keyboard(lang))
        return

    lines = [get_text("transactions_header", lang)]
    for r in rows:
        key = f"tx_type_{r['type']}"
        type_label = get_text(key, lang) if key in STRINGS else r["type"]
        icon = TX_ICONS.get(r["type"], "•")
        sign = "+" if r["amount"] >= 0 else ""
        lines.append(get_text(
            "tx_row", lang,
            icon=icon, type_label=type_label, sign=sign, amount=fmt(abs(r["amount"])),
            date=r["created_at"][:16].replace("T", " "),
        ))

    await safe_edit(query, "\n".join(lines), reply_markup=back_keyboard(lang))


async def handle_daily_bonus(query, db_user):
    lang = lang_of(db_user)
    user_id = db_user["user_id"]
    can_claim, hours_remaining = db.can_claim_daily_bonus(user_id)

    if can_claim:
        balance = db.adjust_balance(user_id, config.DAILY_BONUS_AMOUNT)
        db.record_transaction(user_id, "daily_bonus", config.DAILY_BONUS_AMOUNT, status="completed")
        db.set_daily_bonus_claimed(user_id)
        await safe_edit(
            query,
            get_text("daily_bonus_claimed", lang, amount=fmt(config.DAILY_BONUS_AMOUNT), balance=fmt(balance)),
            reply_markup=back_keyboard(lang),
        )
    else:
        await safe_edit(query, get_text("daily_bonus_wait", lang, hours=hours_remaining), reply_markup=back_keyboard(lang))


async def handle_referral_info(query, db_user):
    lang = lang_of(db_user)
    user_id = db_user["user_id"]
    link = f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"
    count = db.count_referrals(user_id)
    await safe_edit(
        query,
        get_text(
            "referral_info", lang, link=link,
            signup_bonus=fmt(config.SIGNUP_BONUS), referral_bonus=fmt(config.REFERRAL_BONUS), count=count,
        ),
        reply_markup=back_keyboard(lang),
    )


# =====================================================================
# ROOM ENTRY / CARD SELECTION / PURCHASE
# =====================================================================

def _selection_key(room_fee):
    return f"selected_cards_{room_fee}"


async def enter_room(query, context, db_user, room_fee):
    lang = lang_of(db_user)
    game = db.get_or_create_active_game(room_fee)

    if game["state"] == "running":
        # A game is already in progress for this room - tell the player
        # to wait for the current round to finish rather than letting
        # them buy into a game whose calling has already started.
        await query.answer(get_text("room_busy_alert", lang), show_alert=True)
        return

    context.user_data[_selection_key(room_fee)] = set()
    context.user_data["current_room_fee"] = room_fee
    context.user_data["current_game_id"] = game["id"]

    await show_card_page(query, context, db_user, page=0)


async def show_card_page(query, context, db_user, page):
    lang = lang_of(db_user)
    room_fee = context.user_data.get("current_room_fee")
    game_id = context.user_data.get("current_game_id")
    if room_fee is None or game_id is None:
        await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    selected = context.user_data.get(_selection_key(room_fee), set())
    game = db.get_game(game_id)
    sold = db.count_cards_sold(game_id)

    header = get_text(
        "card_select_header", lang,
        fee=fmt(room_fee), balance=fmt(db_user["balance"]), pool=fmt(game["pool"]),
        sold=sold, last_buyer=get_last_buyer_label(game_id), countdown="-",
        max_cards=config.MAX_CARDS_PER_PLAYER,
    )

    await safe_edit(query, header, reply_markup=build_card_page_keyboard(game_id, room_fee, lang, page, selected))
    context.user_data["current_page"] = page


async def toggle_card_selection(query, context, db_user, idx):
    lang = lang_of(db_user)
    room_fee = context.user_data.get("current_room_fee")
    game_id = context.user_data.get("current_game_id")
    if room_fee is None or game_id is None:
        await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    taken = db.get_taken_cards(game_id)
    if idx in taken:
        await query.answer(get_text("card_taken", lang, num=idx + 1), show_alert=True)
        return

    selected = context.user_data.setdefault(_selection_key(room_fee), set())

    if idx in selected:
        selected.discard(idx)
    else:
        if len(selected) >= config.MAX_CARDS_PER_PLAYER:
            await query.answer(get_text("max_cards_exceeded", lang, max=config.MAX_CARDS_PER_PLAYER), show_alert=True)
            return
        selected.add(idx)

    page = context.user_data.get("current_page", 0)
    await show_card_page(query, context, db_user, page)


async def random_pick(query, context, db_user, count):
    lang = lang_of(db_user)
    room_fee = context.user_data.get("current_room_fee")
    game_id = context.user_data.get("current_game_id")
    if room_fee is None or game_id is None:
        await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    taken = db.get_taken_cards(game_id)
    selected = context.user_data.setdefault(_selection_key(room_fee), set())

    available = [i for i in range(config.CARD_POOL_SIZE) if i not in taken and i not in selected]
    import random as _random
    _random.shuffle(available)

    room_for_more = config.MAX_CARDS_PER_PLAYER - len(selected)
    to_add = available[:min(count, room_for_more)]

    if not to_add and room_for_more <= 0:
        await query.answer(get_text("max_cards_exceeded", lang, max=config.MAX_CARDS_PER_PLAYER), show_alert=True)
        return

    selected.update(to_add)
    page = context.user_data.get("current_page", 0)
    await show_card_page(query, context, db_user, page)


async def confirm_purchase(query, context, db_user):
    lang = lang_of(db_user)
    user_id = db_user["user_id"]
    room_fee = context.user_data.get("current_room_fee")
    game_id = context.user_data.get("current_game_id")
    selected = context.user_data.get(_selection_key(room_fee), set())

    if not selected:
        await query.answer(get_text("no_cards_selected", lang), show_alert=True)
        return

    success, reason = db.purchase_cards(game_id, user_id, list(selected), room_fee)

    if not success:
        if reason == "insufficient_balance":
            needed = room_fee * len(selected)
            await query.answer(
                get_text("insufficient_balance_buy", lang, needed=fmt(needed), have=fmt(db_user["balance"])),
                show_alert=True,
            )
        elif reason == "card_taken":
            # The DB call fails atomically without telling us which specific
            # index collided (another player could have grabbed any of our
            # selected cards a moment ago) - num=0 displays as "#0" which
            # would be misleading, so use the lowest selected index as a
            # representative placeholder and rely on the page refresh below
            # to show the player exactly which cards are now unavailable.
            first_selected = min(selected) + 1
            await query.answer(get_text("card_taken", lang, num=first_selected), show_alert=True)
            # Refresh the page so the now-stale "taken" state is visible
            page = context.user_data.get("current_page", 0)
            await show_card_page(query, context, db_user, page)
        elif reason == "max_cards_exceeded":
            await query.answer(get_text("max_cards_exceeded", lang, max=config.MAX_CARDS_PER_PLAYER), show_alert=True)
        else:
            await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    context.user_data[_selection_key(room_fee)] = set()
    new_balance = db.get_balance(user_id)
    await query.answer("OK")  # lightweight ack; the lobby screen render below shows full detail

    # Register this player's live message for the upcoming game loop -
    # we reuse the SAME message (the one with the card grid) by editing
    # it into the "waiting for game to start" lobby screen.
    db.upsert_game_player_message(game_id, user_id, query.message.chat_id, query.message.message_id)

    await render_lobby_screen(context.bot, game_id, user_id, lang)

    # Ensure a lifecycle task is running for this room now that someone
    # has bought in (guarded so only ONE task per room can ever exist).
    await ensure_game_lifecycle_started(context, room_fee, game_id)


# =====================================================================
# GAME LIFECYCLE ENGINE
# One asyncio task per room drives: countdown -> (refund OR run game)
# -> resolve winners -> reset room for the next round.
# =====================================================================

def get_last_buyer_label(game_id) -> str:
    cards = db.get_all_game_cards(game_id)
    if not cards:
        return "-"
    last = max(cards, key=lambda c: c["created_at"])
    owner = db.get_user(last["owner_id"])
    name = owner["username"] if owner else str(last["owner_id"])
    return bingo.mask_username(name, config.MASK_VISIBLE_CHARS)


async def render_lobby_screen(bot, game_id, user_id, lang, countdown_remaining=None):
    """Render the 'waiting for game to start' screen into ONE player's
    message. Called in a loop over every seated player by the
    countdown ticker so all of them see a synchronized live countdown."""
    game = db.get_game(game_id)
    sold = db.count_cards_sold(game_id)
    gp = db.get_game_player(game_id, user_id)
    if gp is None or gp["chat_id"] is None:
        return

    countdown_text = str(countdown_remaining) if countdown_remaining is not None else str(config.COUNTDOWN_SECONDS)

    text = get_text(
        "lobby_waiting", lang,
        pool=fmt(game["pool"]), sold=sold, countdown=countdown_text,
        min_cards=config.MIN_CARDS_TO_START,
    )
    await safe_edit_by_id(bot, gp["chat_id"], gp["message_id"], text)


async def broadcast_lobby_tick(bot, game_id, seconds_remaining):
    """Push the current countdown to every seated player's message."""
    players = db.get_game_players(game_id)
    for p in players:
        user = db.get_user(p["user_id"])
        lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
        await render_lobby_screen(bot, game_id, p["user_id"], lang, countdown_remaining=seconds_remaining)


async def ensure_game_lifecycle_started(context, room_fee, game_id):
    """Spawn the countdown/game asyncio task for this room IF one isn't
    already running. Guarded by a per-room lock so two near-simultaneous
    purchases can't both spawn duplicate tasks."""
    lock = ROOM_LOCKS[room_fee]
    async with lock:
        existing_task = ACTIVE_GAME_TASKS.get(room_fee)
        if existing_task is not None and not existing_task.done():
            return  # already running, nothing to do

        sold = db.count_cards_sold(game_id)
        if sold < 1:
            return  # nothing to start yet

        task = asyncio.create_task(run_game_lifecycle(context, room_fee, game_id))
        ACTIVE_GAME_TASKS[room_fee] = task


async def run_game_lifecycle(context, room_fee, game_id):
    """The full lifecycle for one room's round:
      1. Countdown for config.COUNTDOWN_SECONDS, ticking every player's
         lobby screen each second.
      2. At countdown end: if fewer than MIN_CARDS_TO_START cards sold,
         refund everyone and reset the room (new 'waiting' game created
         on next purchase - we don't pre-create it here to avoid an
         empty game row sitting around indefinitely).
      3. Otherwise: mark game 'running', then call numbers one at a
         time (config.CALL_DELAY_SECONDS apart), pushing the live
         board to every player after each call, auto-claiming for any
         player with AUTO ON the instant they have a valid win.
      4. On win (manual BINGO claim OR auto-claim) OR exhausting all 75
         calls with no winner: resolve the round (split pot among any
         simultaneous winners, or refund everyone if no winner) and
         finish the game.
      5. A fresh 'waiting' game is created for the room so the next
         purchase has somewhere to land.
    """
    bot = context.bot
    try:
        # ---- PHASE A: COUNTDOWN ----
        for remaining in range(config.COUNTDOWN_SECONDS, 0, -1):
            await asyncio.sleep(1)
            sold = db.count_cards_sold(game_id)
            # Only bother ticking the UI every player sees if anyone's
            # actually seated - cheap early-exit guard.
            if sold > 0:
                await broadcast_lobby_tick(bot, game_id, remaining)

        sold = db.count_cards_sold(game_id)
        if sold < config.MIN_CARDS_TO_START:
            await handle_insufficient_players_refund(bot, game_id)
            return

        # ---- PHASE B: RUN THE GAME ----
        db.set_game_state(game_id, "running")
        await broadcast_game_starting(bot, game_id)

        call_sequence = bingo.generate_call_sequence()
        called_numbers = []
        winners_found = {}  # user_id -> {card_index: win_type}
        GAME_MANUAL_CLAIMS[game_id] = {}

        for call_index, number in enumerate(call_sequence[: config.MAX_NUMBERS_CALLED], start=1):
            called_numbers.append(number)
            db.add_called_number(game_id, call_index, number)

            auto_winners = await push_call_and_check_wins(bot, game_id, called_numbers, call_index)

            # Merge in anything a player claimed manually via the BINGO
            # button since the last call - re-validate against the
            # CURRENT called_numbers in case the claim was stale (e.g.
            # pressed right as a new number was being called).
            manual_claims = GAME_MANUAL_CLAIMS.get(game_id, {})
            for claim_user_id, claimed_cards in list(manual_claims.items()):
                revalidated = bingo.evaluate_player_cards_detailed(claimed_cards, called_numbers)
                if revalidated:
                    auto_winners.setdefault(claim_user_id, {}).update(revalidated)

            winners_found = auto_winners
            if winners_found:
                break

        # ---- PHASE C: RESOLVE ----
        if winners_found:
            await resolve_round_winners(bot, game_id, room_fee, winners_found)
        else:
            await resolve_round_no_winner(bot, game_id, room_fee, called_numbers)

    except Exception:
        logger.exception(f"Game lifecycle crashed for room {room_fee}, game {game_id}")
        # Best-effort safety net: refund everyone rather than leave money
        # in limbo if something unexpected blew up mid-round.
        try:
            db.refund_game(game_id)
            db.set_game_state(game_id, "finished")
        except Exception:
            logger.exception("Refund-on-crash ALSO failed - manual DB check needed")
    finally:
        # Always leave a fresh waiting game for this room so the next
        # purchase has somewhere to land, and clear the task slot.
        db.get_or_create_active_game(room_fee)
        ACTIVE_GAME_TASKS.pop(room_fee, None)
        GAME_MANUAL_CLAIMS.pop(game_id, None)


async def handle_insufficient_players_refund(bot, game_id):
    refunded = db.refund_game(game_id)
    db.set_game_state(game_id, "finished")

    for user_id, amount in refunded.items():
        user = db.get_user(user_id)
        lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
        gp = db.get_game_player(game_id, user_id)
        text = get_text("lobby_refund", lang, amount=fmt(amount))
        if gp and gp["chat_id"]:
            await safe_edit_by_id(bot, gp["chat_id"], gp["message_id"], text, reply_markup=back_keyboard(lang))


async def broadcast_game_starting(bot, game_id):
    players = db.get_game_players(game_id)
    for p in players:
        user = db.get_user(p["user_id"])
        lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
        if p["chat_id"]:
            try:
                await bot.send_message(chat_id=p["chat_id"], text=get_text("game_starting", lang), parse_mode="HTML")
            except Forbidden:
                pass


async def push_call_and_check_wins(bot, game_id, called_numbers, call_index):
    """Push the latest called number + updated board to every seated
    player, and for anyone with AUTO ON, check their cards immediately
    and treat a detected win as an instant claim.

    Returns a dict: {user_id: {card_index: win_type}} containing ONLY
    the winners detected on THIS call (empty dict if none) - this is
    what the outer loop uses to decide whether to stop calling.

    Manual BINGO claims (button presses) are handled separately in
    game_bingo_claim() and write into a shared 'pending_manual_claims'
    structure in bot_data so they get folded into the same resolution
    step if they land within this call's processing.
    """
    players = db.get_game_players(game_id)
    game = db.get_game(game_id)
    auto_winners = {}

    number = called_numbers[-1]
    announcement = bingo.format_call_announcement(number)

    for p in players:
        user_id = p["user_id"]
        user = db.get_user(user_id)
        lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
        if not p["chat_id"]:
            continue

        card_indices = db.get_player_cards(game_id, user_id)
        header = get_text(
            "game_header", lang, fee=fmt(game["room_fee"]),
            called=call_index, total=config.MAX_NUMBERS_CALLED, pool=fmt(game["pool"]), players=len(players),
        )
        number_line = get_text("number_called", lang, letter=bingo.number_to_letter(number), number=number, amharic=bingo.number_to_amharic(number))

        grid = bingo.render_number_grid_html(called_numbers)
        cards_html = "\n\n".join(
            bingo.render_card_html_with_label(idx, bingo.get_card(idx), called_numbers)
            for idx in card_indices
        )

        full_text = f"{header}{number_line}\n\n{grid}\n\n{cards_html}"

        await safe_edit_by_id(
            bot, p["chat_id"], p["message_id"], full_text,
            reply_markup=active_game_keyboard(lang, auto_win_on=bool(p["auto_win"]), marked_count=len(called_numbers), total_called=len(called_numbers)),
        )

        if p["auto_win"]:
            detected = bingo.evaluate_player_cards_detailed(card_indices, called_numbers)
            if detected:
                auto_winners[user_id] = detected

    return auto_winners


async def resolve_round_winners(bot, game_id, room_fee, winners_found):
    """winners_found: {user_id: {card_index: win_type}}.
    Pays out: house takes its commission, the remainder is split EQUALLY
    among every winning user_id (one share per USER, not per winning
    card, per product decision - corners and line pay identically and
    a simultaneous claim of either type splits the pot the same way)."""
    game = db.get_game(game_id)
    pool = game["pool"]
    house_cut = round(pool * config.HOUSE_COMMISSION_PERCENT / 100, 2)
    remaining = round(pool - house_cut, 2)

    winner_ids = list(winners_found.keys())
    per_winner_amount = round(remaining / len(winner_ids), 2)

    db.finish_game(game_id, winner_ids, house_cut, per_winner_amount)
    db.credit_house(house_cut)

    for user_id in winner_ids:
        new_balance = db.adjust_balance(user_id, per_winner_amount)
        db.record_transaction(user_id, "bingo_win", per_winner_amount, status="completed")

    winner_label_list = []
    for user_id in winner_ids:
        user = db.get_user(user_id)
        name = user["username"] if user else str(user_id)
        winner_label_list.append(bingo.mask_username(name, config.MASK_VISIBLE_CHARS))
    winner_list_str = ", ".join(winner_label_list)

    players = db.get_game_players(game_id)
    for p in players:
        user_id = p["user_id"]
        user = db.get_user(user_id)
        lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
        if not p["chat_id"]:
            continue

        if user_id in winners_found:
            card_indices_won = list(winners_found[user_id].keys())
            card_num_display = card_indices_won[0] + 1
            new_balance = db.get_balance(user_id)

            if len(winner_ids) == 1:
                win_type = list(winners_found[user_id].values())[0]
                key = "win_corners" if win_type == "corners" else "win_line"
                text = get_text(key, lang, username=bingo.mask_username(user["username"] if user else "", config.MASK_VISIBLE_CHARS),
                                 amount=fmt(per_winner_amount), card_num=card_num_display, balance=fmt(new_balance))
            else:
                text = get_text("win_split", lang, winner_count=len(winner_ids), amount=fmt(per_winner_amount),
                                 card_num=card_num_display, balance=fmt(new_balance))
        else:
            if len(winner_ids) == 1:
                win_user_id = winner_ids[0]
                win_user = db.get_user(win_user_id)
                win_name = bingo.mask_username(win_user["username"] if win_user else "", config.MASK_VISIBLE_CHARS)
                win_type = list(winners_found[win_user_id].values())[0]
                win_type_label = get_text("win_type_corners", lang) if win_type == "corners" else get_text("win_type_line", lang)
                card_num_display = list(winners_found[win_user_id].keys())[0] + 1
                text = get_text("win_announce_others", lang, username=win_name, amount=fmt(per_winner_amount),
                                 card_num=card_num_display, win_type=win_type_label)
            else:
                text = get_text("win_split_announce_others", lang, winner_count=len(winner_ids),
                                 amount=fmt(per_winner_amount), winner_list=winner_list_str)

        await safe_edit_by_id(bot, p["chat_id"], p["message_id"], text, reply_markup=play_again_keyboard(lang, room_fee))


async def resolve_round_no_winner(bot, game_id, room_fee, called_numbers):
    """All 75 numbers called, nobody won - full refund to everyone."""
    refunded = db.refund_game(game_id)
    db.finish_game(game_id, [], 0, 0)

    for user_id, amount in refunded.items():
        user = db.get_user(user_id)
        lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
        gp = db.get_game_player(game_id, user_id)
        if gp and gp["chat_id"]:
            text = get_text("no_winner_refund", lang, amount=fmt(amount))
            await safe_edit_by_id(bot, gp["chat_id"], gp["message_id"], text, reply_markup=play_again_keyboard(lang, room_fee))


# =====================================================================
# IN-GAME BUTTON HANDLERS (Check All / Auto toggle / BINGO claim)
# =====================================================================

def _find_user_active_game(user_id):
    """A player only has ONE game they can be actively seated in across
    all rooms at a time (cards are purchased per-room, and rooms run
    independently, but in practice a player waits for one round before
    joining another). Find the game_id + room_fee for whichever room
    this user currently has a game_players row with state running/waiting."""
    for fee in config.ROOM_FEES:
        game = db.get_or_create_active_game(fee)
        gp = db.get_game_player(game["id"], user_id)
        if gp is not None:
            return game["id"], fee
    return None, None


async def game_check_all(query, context, db_user):
    """Manually re-render the player's own cards/board on demand -
    mostly useful as a 'refresh' if their message somehow got out of
    sync, since the loop already auto-pushes after every call."""
    lang = lang_of(db_user)
    user_id = db_user["user_id"]
    game_id, room_fee = _find_user_active_game(user_id)
    if game_id is None:
        await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    called_numbers = db.get_called_numbers(game_id)
    card_indices = db.get_player_cards(game_id, user_id)
    game = db.get_game(game_id)
    players = db.get_game_players(game_id)
    gp = db.get_game_player(game_id, user_id)

    header = get_text(
        "game_header", lang, fee=fmt(room_fee),
        called=len(called_numbers), total=config.MAX_NUMBERS_CALLED,
        pool=fmt(game["pool"]), players=len(players),
    )
    grid = bingo.render_number_grid_html(called_numbers)
    cards_html = "\n\n".join(
        bingo.render_card_html_with_label(idx, bingo.get_card(idx), called_numbers)
        for idx in card_indices
    )
    text = f"{header}{grid}\n\n{cards_html}"

    await safe_edit(query, text, reply_markup=active_game_keyboard(lang, auto_win_on=bool(gp["auto_win"]), marked_count=len(called_numbers), total_called=len(called_numbers)))


async def game_toggle_auto(query, context, db_user):
    lang = lang_of(db_user)
    user_id = db_user["user_id"]
    game_id, room_fee = _find_user_active_game(user_id)
    if game_id is None:
        await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    gp = db.get_game_player(game_id, user_id)
    new_value = not bool(gp["auto_win"])
    db.set_auto_win(game_id, user_id, new_value)

    await query.answer(get_text("auto_win_on", lang) if new_value else get_text("auto_win_off", lang))
    await game_check_all(query, context, db_user)


async def game_bingo_claim(query, context, db_user):
    """Manual BINGO button press. Validates the claim against the
    numbers called SO FAR (read from DB, always authoritative) and, if
    valid, registers it into GAME_MANUAL_CLAIMS so the calling loop
    picks it up and resolves the round. If invalid, tells the player
    without disrupting the game for anyone else."""
    lang = lang_of(db_user)
    user_id = db_user["user_id"]
    game_id, room_fee = _find_user_active_game(user_id)
    if game_id is None:
        await query.answer(get_text("error_generic", lang), show_alert=True)
        return

    game = db.get_game(game_id)
    if game["state"] != "running":
        await query.answer(get_text("game_not_running", lang), show_alert=True)
        return

    called_numbers = db.get_called_numbers(game_id)
    card_indices = db.get_player_cards(game_id, user_id)
    detected = bingo.evaluate_player_cards_detailed(card_indices, called_numbers)

    if not detected:
        await query.answer(get_text("bingo_claim_invalid", lang), show_alert=True)
        return

    GAME_MANUAL_CLAIMS.setdefault(game_id, {})[user_id] = card_indices
    await query.answer(get_text("bingo_claim_accepted", lang), show_alert=True)


# =====================================================================
# DEPOSIT FLOW (pick amount -> show account -> paste SMS -> verify)
# =====================================================================

async def menu_deposit_entry(query, context, db_user):
    lang = lang_of(db_user)
    await safe_edit(query, get_text("deposit_pick_amount", lang), reply_markup=deposit_amount_keyboard(lang))


async def deposit_amount_chosen(query, context, db_user, data):
    lang = lang_of(db_user)

    if data == "depamt_custom":
        await safe_edit(query, get_text("deposit_custom_prompt", lang, min=fmt(config.MIN_DEPOSIT)))
        context.user_data["awaiting_custom_deposit"] = True
        return DEPOSIT_CUSTOM_AMOUNT

    amount = float(data.split("_", 1)[1])
    await show_deposit_account(query, context, db_user, amount)
    return ConversationHandler.END


async def custom_deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)
    amount = safe_amount(update.message.text)

    if amount is None or amount < config.MIN_DEPOSIT:
        await update.message.reply_text(get_text("deposit_amount_too_low", lang, min=fmt(config.MIN_DEPOSIT)))
        return DEPOSIT_CUSTOM_AMOUNT

    context.user_data["pending_deposit_amount"] = amount
    context.user_data.pop("awaiting_custom_deposit", None)

    account = db.get_active_deposit_account()
    if account is None:
        await update.message.reply_text(get_text("deposit_no_account", lang))
        return ConversationHandler.END

    text = get_text(
        "deposit_instructions", lang, amount=fmt(amount),
        telebirr_number=account["phone"], recipient_name=account["recipient_name"],
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=back_keyboard(lang))
    return ConversationHandler.END


async def show_deposit_account(query, context, db_user, amount):
    lang = lang_of(db_user)
    context.user_data["pending_deposit_amount"] = amount

    account = db.get_active_deposit_account()
    if account is None:
        await safe_edit(query, get_text("deposit_no_account", lang), reply_markup=back_keyboard(lang))
        return

    text = get_text(
        "deposit_instructions", lang, amount=fmt(amount),
        telebirr_number=account["phone"], recipient_name=account["recipient_name"],
    )
    await safe_edit(query, text, reply_markup=back_keyboard(lang))


async def handle_possible_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches any free-text message that isn't part of an active
    conversation - checks if it looks like a pasted Telebirr SMS."""
    text = update.message.text
    user = update.effective_user
    db_user = db.get_user(user.id)
    if db_user is None:
        return
    lang = lang_of(db_user)

    if "ETB" not in text.upper():
        return  # not an SMS-looking message; silently ignore rather than
                 # spam unrelated chatter with an error

    account = db.get_active_deposit_account()
    if account is None:
        await update.message.reply_text(get_text("deposit_no_account", lang))
        return

    parsed = parse_telebirr_sms(text)
    if parsed is None:
        await update.message.reply_text(get_text("deposit_invalid", lang))
        return

    expected_last4 = account["phone"][-4:]
    ok, reason = verify_recipient(parsed, account["recipient_name"], expected_last4)
    if not ok:
        await update.message.reply_text(
            get_text("deposit_wrong_account", lang, telebirr_number=account["phone"], recipient_name=account["recipient_name"])
        )
        return

    if db.reference_already_used(parsed["reference"]):
        await update.message.reply_text(get_text("deposit_already_used", lang))
        return

    pending_amount = context.user_data.get("pending_deposit_amount")
    if pending_amount is not None:
        amount_ok, amount_reason = validate_deposit_amount(parsed, expected_amount=pending_amount)
        if not amount_ok:
            await update.message.reply_text(
                get_text("deposit_amount_mismatch", lang, expected_amount=fmt(pending_amount), sms_amount=fmt(parsed["amount"]))
            )
            return

    new_balance = db.adjust_balance(user.id, parsed["amount"])
    db.record_transaction(user.id, "deposit", parsed["amount"], reference=parsed["reference"], status="completed")
    db.record_deposit_for_account(account["id"])
    context.user_data.pop("pending_deposit_amount", None)

    await update.message.reply_text(
        get_text("deposit_success", lang, amount=fmt(parsed["amount"]), balance=fmt(new_balance)),
        parse_mode="HTML", reply_markup=main_menu_keyboard(lang),
    )

    # Referral bonus: only on this user's FIRST completed deposit
    db_user = db.get_user(user.id)
    if (
        db_user["referred_by"] is not None
        and db_user["referral_bonus_given"] == 0
        and db.count_deposits(user.id) == 1
    ):
        referrer_id = db_user["referred_by"]
        referrer_balance = db.adjust_balance(referrer_id, config.REFERRAL_BONUS)
        db.record_transaction(referrer_id, "referral_bonus", config.REFERRAL_BONUS, status="completed")
        db.mark_referral_bonus_given(user.id)

        referrer = db.get_user(referrer_id)
        ref_lang = lang_of(referrer) if referrer else config.DEFAULT_LANGUAGE
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=get_text(
                    "referral_bonus_earned", ref_lang,
                    username=html.escape(db_user["username"] or str(user.id)),
                    amount=fmt(config.REFERRAL_BONUS), balance=fmt(referrer_balance),
                ),
                parse_mode="HTML",
            )
        except Forbidden:
            pass


# =====================================================================
# WITHDRAWAL FLOW (conversation, entry point = "menu_withdraw" button)
# =====================================================================

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)

    if not db_user["phone"]:
        await safe_edit(query, get_text("withdraw_no_phone", lang), reply_markup=back_keyboard(lang))
        return ConversationHandler.END

    if db_user["balance"] < config.MIN_WITHDRAWAL:
        await safe_edit(
            query, get_text("withdraw_insufficient", lang, balance=fmt(db_user["balance"])),
            reply_markup=back_keyboard(lang),
        )
        return ConversationHandler.END

    await safe_edit(query, get_text("withdraw_start", lang, balance=fmt(db_user["balance"]), phone=db_user["phone"], min=fmt(config.MIN_WITHDRAWAL)))
    return WITHDRAW_AMOUNT


async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)
    amount = safe_amount(update.message.text)

    if amount is None:
        await update.message.reply_text(get_text("withdraw_invalid_amount", lang))
        return WITHDRAW_AMOUNT

    if amount < config.MIN_WITHDRAWAL:
        await update.message.reply_text(get_text("withdraw_below_min", lang, min=fmt(config.MIN_WITHDRAWAL)))
        return WITHDRAW_AMOUNT

    if amount > db_user["balance"]:
        await update.message.reply_text(get_text("withdraw_insufficient", lang, balance=fmt(db_user["balance"])))
        return ConversationHandler.END

    # Deduct balance immediately (atomic) so the same request can't be
    # submitted twice before admin processes it. Withdrawals go to the
    # user's REGISTERED phone (collected at /start) - never user-typed
    # at this step, which removes the risk of funds being redirected to
    # an unverified number.
    new_balance = db.adjust_balance(user.id, -amount)
    withdrawal_id = db.create_withdrawal(user.id, amount, db_user["phone"])
    db.record_transaction(user.id, "withdraw", -amount, reference=f"withdraw_{withdrawal_id}", status="pending")

    await update.message.reply_text(
        get_text("withdraw_submitted", lang, amount=fmt(amount), phone=db_user["phone"]),
        parse_mode="HTML", reply_markup=main_menu_keyboard(lang),
    )

    for admin_id in config.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=get_text(
                    "withdraw_admin_notify", "en",
                    id=withdrawal_id, user_id=user.id, username=html.escape(db_user["username"] or ""),
                    amount=fmt(amount), phone=db_user["phone"],
                    time=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                ),
                parse_mode="HTML", reply_markup=withdraw_approval_keyboard(withdrawal_id),
            )
        except Forbidden:
            logger.warning(f"Could not notify admin {admin_id} - they may not have started the bot")

    return ConversationHandler.END


async def withdraw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = db.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    await update.message.reply_text(get_text("cancel", lang), reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def admin_approve_withdrawal(query, context, withdrawal_id):
    if query.from_user.id not in config.ADMIN_IDS:
        await query.answer("Not authorized", show_alert=True)
        return

    withdrawal = db.get_withdrawal(withdrawal_id)
    if withdrawal is None or withdrawal["status"] != "pending":
        await query.answer("Already processed or not found", show_alert=True)
        return

    db.update_withdrawal_status(withdrawal_id, "approved")
    await safe_edit(query, f"✅ Withdrawal #{withdrawal_id} approved.", parse_mode="HTML")

    user = db.get_user(withdrawal["user_id"])
    lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
    try:
        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=get_text("withdraw_approved", lang, amount=fmt(withdrawal["amount"]), phone=withdrawal["phone"]),
            parse_mode="HTML",
        )
    except Forbidden:
        pass


async def admin_reject_withdrawal(query, context, withdrawal_id):
    if query.from_user.id not in config.ADMIN_IDS:
        await query.answer("Not authorized", show_alert=True)
        return

    withdrawal = db.get_withdrawal(withdrawal_id)
    if withdrawal is None or withdrawal["status"] != "pending":
        await query.answer("Already processed or not found", show_alert=True)
        return

    # Refund the user since the withdrawal was rejected
    db.adjust_balance(withdrawal["user_id"], withdrawal["amount"])
    db.record_transaction(withdrawal["user_id"], "withdraw_refund", withdrawal["amount"], status="completed")
    db.update_withdrawal_status(withdrawal_id, "rejected")
    await safe_edit(query, f"❌ Withdrawal #{withdrawal_id} rejected and refunded.", parse_mode="HTML")

    user = db.get_user(withdrawal["user_id"])
    lang = lang_of(user) if user else config.DEFAULT_LANGUAGE
    try:
        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=get_text("withdraw_rejected", lang, amount=fmt(withdrawal["amount"])),
            parse_mode="HTML",
        )
    except Forbidden:
        pass


# =====================================================================
# TRANSFER FLOW (conversation, entry point = "menu_transfer" button)
# =====================================================================

async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)

    can, seconds_remaining = db.can_transfer(user.id)
    if not can:
        minutes_remaining = max(1, seconds_remaining // 60)
        await safe_edit(
            query, get_text("transfer_cooldown", lang, minutes=minutes_remaining),
            reply_markup=back_keyboard(lang),
        )
        return ConversationHandler.END

    if db_user["balance"] < config.MIN_TRANSFER:
        await safe_edit(
            query, get_text("transfer_insufficient", lang, balance=fmt(db_user["balance"])),
            reply_markup=back_keyboard(lang),
        )
        return ConversationHandler.END

    await safe_edit(query, get_text("transfer_start", lang, balance=fmt(db_user["balance"]), min=fmt(config.MIN_TRANSFER)))
    return TRANSFER_USERNAME


async def transfer_username_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)
    target_username = update.message.text.strip().lstrip("@")

    target_row = db.find_user_by_username(target_username)

    if target_row is None:
        await update.message.reply_text(get_text("transfer_user_not_found", lang, username=html.escape(target_username)))
        return TRANSFER_USERNAME

    if target_row["user_id"] == user.id:
        await update.message.reply_text(get_text("transfer_cannot_self", lang))
        return TRANSFER_USERNAME

    context.user_data["transfer_target_id"] = target_row["user_id"]
    context.user_data["transfer_target_username"] = target_username
    await update.message.reply_text(get_text("transfer_enter_amount", lang, to_username=html.escape(target_username), balance=fmt(db_user["balance"])))
    return TRANSFER_AMOUNT


async def transfer_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)
    lang = lang_of(db_user)
    amount = safe_amount(update.message.text)

    target_id = context.user_data.get("transfer_target_id")
    target_username = context.user_data.get("transfer_target_username", "")

    if target_id is None:
        await update.message.reply_text(get_text("error_generic", lang))
        return ConversationHandler.END

    if amount is None:
        await update.message.reply_text(get_text("transfer_invalid_amount", lang))
        return TRANSFER_AMOUNT

    if amount < config.MIN_TRANSFER:
        await update.message.reply_text(get_text("transfer_below_min", lang, min=fmt(config.MIN_TRANSFER)))
        return TRANSFER_AMOUNT

    success, reason = db.transfer_funds(user.id, target_id, amount)

    if not success:
        if reason == "insufficient_balance":
            await update.message.reply_text(get_text("transfer_insufficient", lang))
        else:
            await update.message.reply_text(get_text("error_generic", lang))
        return ConversationHandler.END

    new_balance = db.get_balance(user.id)
    await update.message.reply_text(
        get_text("transfer_success", lang, amount=fmt(amount), to_username=html.escape(target_username), balance=fmt(new_balance)),
        parse_mode="HTML", reply_markup=main_menu_keyboard(lang),
    )

    target_user = db.get_user(target_id)
    target_lang = lang_of(target_user) if target_user else config.DEFAULT_LANGUAGE
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=get_text(
                "transfer_received", target_lang, amount=fmt(amount),
                from_username=html.escape(db_user["username"] or str(user.id)),
                balance=fmt(db.get_balance(target_id)),
            ),
            parse_mode="HTML",
        )
    except Forbidden:
        pass

    context.user_data.pop("transfer_target_id", None)
    context.user_data.pop("transfer_target_username", None)
    return ConversationHandler.END


async def transfer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = db.get_user(update.effective_user.id)
    lang = lang_of(db_user)
    await update.message.reply_text(get_text("cancel", lang), reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# =====================================================================
# ADMIN PANEL
# =====================================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    await update.message.reply_text("🛠️ <b>Admin Panel</b>", parse_mode="HTML", reply_markup=admin_menu_keyboard())


async def admin_callback(query, context, db_user, data):
    if query.from_user.id not in config.ADMIN_IDS:
        await query.answer("Not authorized", show_alert=True)
        return

    if data == "admin_dashboard":
        await admin_show_dashboard(query)
    elif data == "admin_withdrawals":
        await admin_show_withdrawals(query, context)
    elif data == "admin_accounts":
        await admin_show_accounts(query)
    elif data == "admin_house":
        await admin_show_house(query)
    elif data.startswith("admin_acc_remove_"):
        acc_id = int(data.rsplit("_", 1)[1])
        db.remove_deposit_account(acc_id)
        await admin_show_accounts(query)
    elif data == "admin_back":
        await query.edit_message_text("🛠️ <b>Admin Panel</b>", parse_mode="HTML", reply_markup=admin_menu_keyboard())
    # Note: "admin_broadcast" and "admin_acc_add" are NOT handled here -
    # they are ConversationHandler entry points (see admin_broadcast_entry
    # and admin_add_account_entry) registered separately in main(), since
    # this function is invoked from a plain CallbackQueryHandler whose
    # return value cannot start a conversation state.


async def admin_show_dashboard(query):
    total_games = db.get_total_games_played()
    total_collected = db.get_total_collected()
    net_profit = db.get_house_total_earned()
    total_players = db.get_total_unique_players()
    total_users = db.count_users()
    peak_hours = db.get_peak_hours()

    peak_summary = ", ".join(f"{h}:00 ({c})" for h, c in sorted(peak_hours, key=lambda x: -x[1])[:3]) or "No data yet"

    text = (
        "📊 <b>Dashboard</b>\n\n"
        f"🎮 Total games played: <b>{total_games}</b>\n"
        f"💰 Total deposited: <b>{fmt(total_collected)} ETB</b>\n"
        f"🏛️ Net house profit: <b>{fmt(net_profit)} ETB</b>\n"
        f"👥 Total registered users: <b>{total_users}</b>\n"
        f"🎯 Unique bingo players: <b>{total_players}</b>\n\n"
        f"⏰ Top 3 peak hours (UTC): {peak_summary}"
    )
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]))


async def admin_show_withdrawals(query, context):
    pending = db.get_pending_withdrawals()
    if not pending:
        await safe_edit(query, "💸 No pending withdrawals.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]))
        return

    for w in pending[:10]:  # cap to avoid flooding the admin chat
        user = db.get_user(w["user_id"])
        username = user["username"] if user else str(w["user_id"])
        text = (
            f"🔔 <b>Withdrawal #{w['id']}</b>\n"
            f"👤 User: {w['user_id']} (@{html.escape(username or '')})\n"
            f"📱 Phone: {w['phone']}\n"
            f"💰 Amount: <b>{fmt(w['amount'])} ETB</b>\n"
            f"🕐 {w['created_at'][:16].replace('T', ' ')}"
        )
        await context.bot.send_message(
            chat_id=query.from_user.id, text=text, parse_mode="HTML",
            reply_markup=withdraw_approval_keyboard(w["id"]),
        )
    await query.answer(f"{len(pending)} pending withdrawal(s) sent above.")


async def admin_show_accounts(query):
    accounts = db.list_deposit_accounts()
    lines = ["🏦 <b>Deposit Accounts</b>\n"]
    rows = []
    for acc in accounts:
        marker = "🟢 ACTIVE" if acc["active"] else "⚪"
        lines.append(f"{marker} #{acc['id']}: {acc['phone']} ({html.escape(acc['recipient_name'])}) - {acc['deposit_count']}/{config.ROTATE_AFTER_DEPOSITS} deposits")
        rows.append([InlineKeyboardButton(f"🗑️ Remove #{acc['id']}", callback_data=f"admin_acc_remove_{acc['id']}")])

    rows.append([InlineKeyboardButton("➕ Add Account", callback_data="admin_acc_add")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])

    await safe_edit(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


async def admin_show_house(query):
    balance = db.get_house_balance()
    total_earned = db.get_house_total_earned()
    text = (
        "🏛️ <b>House Wallet</b>\n\n"
        f"💰 Current balance: <b>{fmt(balance)} ETB</b>\n"
        f"📈 Total earned (all-time): <b>{fmt(total_earned)} ETB</b>"
    )
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]))


async def admin_add_account_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["new_account_phone"] = phone
    await update.message.reply_text("👤 Send the recipient name exactly as it appears in YOUR Telebirr SMS:")
    return ADMIN_ADD_ACCOUNT_NAME


async def admin_add_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    phone = context.user_data.pop("new_account_phone", None)
    if phone is None:
        await update.message.reply_text("Something went wrong, please start over with /admin.")
        return ConversationHandler.END

    acc_id = db.add_deposit_account(phone, name)
    await update.message.reply_text(f"✅ Account #{acc_id} added: {phone} ({name})", reply_markup=admin_menu_keyboard())
    return ConversationHandler.END


async def admin_broadcast_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_ids = db.get_all_user_ids()
    sent, failed = 0, 0

    for uid in all_ids:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=uid, photo=update.message.photo[-1].file_id,
                    caption=update.message.caption or "",
                )
            else:
                await context.bot.send_message(chat_id=uid, text=update.message.text)
            sent += 1
        except Forbidden:
            failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # gentle throttle to avoid Telegram flood limits

    await update.message.reply_text(f"📢 Broadcast sent to {sent} users ({failed} failed/blocked).")
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def admin_broadcast_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.ADMIN_IDS:
        await query.answer("Not authorized", show_alert=True)
        return ConversationHandler.END
    await query.edit_message_text("📢 Send me the message (text/photo) to broadcast to all users, or /cancel.")
    return ADMIN_BROADCAST_WAIT


async def admin_add_account_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in config.ADMIN_IDS:
        await query.answer("Not authorized", show_alert=True)
        return ConversationHandler.END
    await query.edit_message_text("📱 Send the new account's phone number (e.g. 0911223344):")
    return ADMIN_ADD_ACCOUNT_PHONE


# =====================================================================
# MAIN
# =====================================================================

def main():
    db.init_db()

    application = Application.builder().token(config.BOT_TOKEN).build()

    # ---- /start + phone collection conversation ----
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE_COLLECT: [MessageHandler(filters.CONTACT, phone_received)],
        },
        fallbacks=[CommandHandler("start", start)],
        name="start_conv",
    )

    # ---- Deposit custom-amount conversation ----
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_amount_chosen, pattern="^depamt_custom$")],
        states={
            DEPOSIT_CUSTOM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_deposit_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", withdraw_cancel)],
        name="deposit_conv",
    )

    # ---- Withdrawal conversation ----
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^menu_withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", withdraw_cancel)],
        name="withdraw_conv",
    )

    # ---- Transfer conversation ----
    transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(transfer_start, pattern="^menu_transfer$")],
        states={
            TRANSFER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_username_received)],
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", transfer_cancel)],
        name="transfer_conv",
    )

    # ---- Admin panel conversation (broadcast + add account need free-text input) ----
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_broadcast_entry, pattern="^admin_broadcast$"),
            CallbackQueryHandler(admin_add_account_entry, pattern="^admin_acc_add$"),
        ],
        states={
            ADMIN_BROADCAST_WAIT: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, admin_broadcast_received)],
            ADMIN_ADD_ACCOUNT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_account_phone)],
            ADMIN_ADD_ACCOUNT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_account_name)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        name="admin_conv",
    )

    application.add_handler(start_conv)
    application.add_handler(CommandHandler("admin", admin_command))

    # Conversation handlers MUST be registered before the generic
    # menu_callback CallbackQueryHandler below, so their entry-point
    # patterns (menu_withdraw, menu_transfer, depamt_custom, admin_*)
    # are claimed by the conversation first. python-telegram-bot tries
    # handlers in registration order within the default group and stops
    # at the first one whose filter matches, so order here is load-bearing.
    application.add_handler(deposit_conv)
    application.add_handler(withdraw_conv)
    application.add_handler(transfer_conv)
    application.add_handler(admin_conv)

    # Generic menu/game/admin-readonly callback router (catches everything
    # NOT claimed by a conversation entry point above).
    application.add_handler(CallbackQueryHandler(menu_callback))

    # Free-text messages not part of any conversation - checked for
    # "looks like a pasted Telebirr SMS".
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_possible_sms))

    logger.info("Habesha Bet bot starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
