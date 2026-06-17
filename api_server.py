# api_server.py
# ============================================
# HABESHA BET - MINI APP API SERVER (FastAPI)
#
# Thin HTTP layer. ALL real logic lives in api_handlers.py; this file
# only:
#   1. Defines routes matching what the React Mini App calls
#   2. Extracts + verifies Telegram initData on every request via
#      telegram_auth.extract_user_id() - this is the ONLY source of
#      truth for "who is making this request." The frontend may also
#      send a user_id in the body for convenience/display, but it is
#      NEVER trusted for authorization - every handler call below uses
#      the verified `auth_user_id`, not anything from the request body.
#   3. Serializes handler results to JSON with the right HTTP status
#
# Runs in the SAME process as bot.py (see bot.py's main(), which starts
# this via uvicorn in a background thread/task alongside run_polling()).
# This guarantees there is only ever one process writing to the SQLite
# database, avoiding the multi-writer corruption risk a separate
# process would introduce.
#
# CORS is enabled permissively (allow_origins=["*"]) because Telegram's
# WebView wrapper origin varies by platform/version and is not worth
# pinning down; the REAL security boundary is initData verification,
# not CORS - CORS only stops browser-based cross-origin reads of
# RESPONSES, it does nothing to stop a forged request from curl, so it
# was never the thing protecting this API in the first place.
# ============================================

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

import config
import api_handlers as handlers
from telegram_auth import extract_user_id, InitDataInvalid

app = FastAPI(title="Habesha Bet Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _auth(x_init_data: Optional[str]) -> int:
    """Shared dependency logic: verify the X-Init-Data header and return
    a trustworthy user_id, or raise a 401 the frontend can recognize and
    react to (e.g. by reopening the Mini App so Telegram reissues fresh
    initData)."""
    if not x_init_data:
        raise HTTPException(status_code=401, detail="missing_init_data")
    try:
        return extract_user_id(x_init_data, bot_token=config.BOT_TOKEN)
    except InitDataInvalid as e:
        raise HTTPException(status_code=401, detail=f"invalid_init_data: {e}")


def _respond(result: dict):
    """Handlers return {"ok": True/False, ...}. Map ok=False to HTTP 400
    so the frontend's generic error handling (anything non-2xx -> show
    error toast) works without inspecting the body, while still
    returning the full body so it CAN inspect `error`/`message` for a
    nicer in-app message."""
    if result.get("ok") is False:
        raise HTTPException(status_code=400, detail=result)
    return result


# =====================================================================
# REQUEST BODY MODELS
# =====================================================================

class SetPhoneBody(BaseModel):
    phone: str


class SetLanguageBody(BaseModel):
    language: str


class BuyCardsBody(BaseModel):
    room_fee: float
    card_indices: List[int]


class ToggleAutoBody(BaseModel):
    game_id: int
    enabled: bool


class MarkNumberBody(BaseModel):
    game_id: int
    card_index: int
    number: int


class ClaimBingoBody(BaseModel):
    game_id: int


class SubmitSmsBody(BaseModel):
    sms_text: str
    expected_amount: Optional[float] = None


class WithdrawBody(BaseModel):
    amount: float


class TransferBody(BaseModel):
    to_username: str
    amount: float


# =====================================================================
# AUTH / BOOTSTRAP
# =====================================================================

@app.get("/api/bootstrap")
def bootstrap(x_init_data: Optional[str] = Header(None), x_username: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    # Telegram's initData already carries a username, but extract_user_id
    # only returns the id (deliberately - it's the only field every
    # endpoint actually needs to be trustworthy). For display purposes
    # we accept whatever username the frontend read out of initData
    # itself and pass it through as a hint; the FIRST bootstrap call for
    # a brand-new user is the only place this matters, since db.get_user
    # is authoritative for every call after that.
    username = x_username or str(user_id)
    return _respond(handlers.handle_bootstrap(user_id, username))


@app.post("/api/set-phone")
def set_phone(body: SetPhoneBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_set_phone(user_id, body.phone))


@app.post("/api/set-language")
def set_language(body: SetLanguageBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_set_language(user_id, body.language))


# =====================================================================
# ROOMS / LOBBY
# =====================================================================

@app.get("/api/rooms")
def get_rooms(x_init_data: Optional[str] = Header(None)):
    _auth(x_init_data)  # rooms are not user-specific, but still require a valid session
    return _respond(handlers.handle_get_rooms())


@app.get("/api/rooms/{room_fee}/cards")
def get_room_cards(room_fee: float, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_get_room_cards(user_id, room_fee))


@app.post("/api/buy-cards")
def buy_cards(body: BuyCardsBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_buy_cards(user_id, body.room_fee, body.card_indices))


# =====================================================================
# LIVE GAME (polled every ~1.5-2s by the frontend while a game runs)
# =====================================================================

@app.get("/api/games/{game_id}/state")
def get_game_state(game_id: int, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_get_game_state(user_id, game_id))


@app.post("/api/toggle-auto-win")
def toggle_auto_win(body: ToggleAutoBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_toggle_auto_win(user_id, body.game_id, body.enabled))


@app.post("/api/mark-number")
def mark_number(body: MarkNumberBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_mark_number(user_id, body.game_id, body.card_index, body.number))


@app.post("/api/claim-bingo")
def claim_bingo(body: ClaimBingoBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_claim_bingo(user_id, body.game_id))


# =====================================================================
# DEPOSIT / WITHDRAW / TRANSFER
# =====================================================================

@app.get("/api/deposit-account")
def get_deposit_account(x_init_data: Optional[str] = Header(None)):
    _auth(x_init_data)
    return _respond(handlers.handle_get_deposit_account())


@app.post("/api/submit-deposit-sms")
def submit_deposit_sms(body: SubmitSmsBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_submit_deposit_sms(user_id, body.sms_text, body.expected_amount))


@app.post("/api/withdraw")
def withdraw(body: WithdrawBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_withdraw(user_id, body.amount))


@app.post("/api/transfer")
def transfer(body: TransferBody, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_transfer(user_id, body.to_username, body.amount))


# =====================================================================
# PROFILE / TRANSACTIONS / REFERRAL / BONUS
# =====================================================================

@app.get("/api/profile")
def get_profile(x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_get_profile(user_id))


@app.get("/api/transactions")
def get_transactions(limit: int = 20, x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_get_transactions(user_id, limit))


@app.get("/api/referral")
def get_referral(x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_get_referral_info(user_id))


@app.post("/api/daily-bonus")
def claim_daily_bonus(x_init_data: Optional[str] = Header(None)):
    user_id = _auth(x_init_data)
    return _respond(handlers.handle_claim_daily_bonus(user_id))


# =====================================================================
# HEALTH CHECK
# Free hosts (Render/Railway) ping a root or /health path to know the
# service is alive - without this many free tiers will mark the
# service unhealthy and cycle/sleep it. Declared BEFORE the static
# mount below for unambiguous route precedence.
# =====================================================================

@app.get("/health")
def health():
    return {"status": "ok"}


# =====================================================================
# STATIC FILE SERVING (the built React Mini App)
#
# One-host deployment: this SAME FastAPI server serves both the JSON
# API under /api/* AND the built frontend (miniapp/dist/ after running
# `npm run build`) at the root. Telegram's Mini App button points at
# this server's root URL, so "/" must return the app's index.html, not
# a JSON response.
#
# StaticFiles with html=True serves index.html for unmatched paths too
# (needed because this is a client-side-routed SPA conceptually, even
# though the current app uses in-memory view state rather than a
# router - if that ever changes to use react-router with real URLs,
# this fallback is what makes refreshing a deep link work).
# =====================================================================

from fastapi.staticfiles import StaticFiles
import pathlib

_DIST_DIR = pathlib.Path(__file__).parent / "miniapp" / "dist"

if _DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="miniapp")
else:
    @app.get("/")
    def root_not_built():
        return {
            "status": "ok",
            "service": "habesha-bet-api",
            "note": "miniapp/dist not found - run `npm run build` inside miniapp/ to serve the frontend from here.",
        }
