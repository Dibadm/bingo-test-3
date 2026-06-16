# bingo.py
# ============================================
# HABESHA BET - BINGO GAME LOGIC
#
# Covers:
#   - 200-card deterministic pool (same cards every restart)
#   - Win detection: Line (row/col/diagonal) + Corners only
#   - Amharic number names 1-75
#   - Text card renderer (monospace, for <pre> tags)
#   - Number-grid renderer (1-75 overview)
#   - Ball sequence generator
#   - Username masking helper
# ============================================

import random

COLUMNS = [
    ("B",  1, 15),
    ("I", 16, 30),
    ("N", 31, 45),
    ("G", 46, 60),
    ("O", 61, 75),
]
LETTERS = [c[0] for c in COLUMNS]
FREE_SPACE = 0  # center cell (col index 2, row index 2)


# =====================================================================
# CARD GENERATION
# =====================================================================

def _generate_one_card(rng: random.Random) -> list:
    """card[col][row], 0-indexed. card[2][2] = FREE_SPACE."""
    card = []
    for i, (_, low, high) in enumerate(COLUMNS):
        nums = rng.sample(range(low, high + 1), 5)
        if i == 2:
            nums[2] = FREE_SPACE
        card.append(nums)
    return card


def generate_card_pool(size: int = 200, seed: int = 20250615) -> list:
    """Generate a fixed-seed pool of unique bingo cards.
    Same seed = same 200 cards every time the bot restarts."""
    rng = random.Random(seed)
    pool = []
    seen = set()
    attempts = 0

    while len(pool) < size and attempts < size * 50:
        card = _generate_one_card(rng)
        fp = tuple(sorted(n for col in card for n in col if n != FREE_SPACE))
        if fp not in seen:
            seen.add(fp)
            pool.append(card)
        attempts += 1

    # Fallback (extremely unlikely with 75-ball rules)
    while len(pool) < size:
        pool.append(_generate_one_card(rng))

    return pool


CARD_POOL = generate_card_pool(200)


def get_card(card_index: int) -> list:
    return CARD_POOL[card_index]


# =====================================================================
# WIN DETECTION
# =====================================================================

def _marked(value: int, called: set) -> bool:
    return value == FREE_SPACE or value in called


def check_line_win(card: list, called: set) -> bool:
    """True if any row, column, or diagonal is fully marked."""
    for col in range(5):
        if all(_marked(card[col][row], called) for row in range(5)):
            return True
    for row in range(5):
        if all(_marked(card[col][row], called) for col in range(5)):
            return True
    if all(_marked(card[i][i], called) for i in range(5)):
        return True
    if all(_marked(card[4 - i][i], called) for i in range(5)):
        return True
    return False


def check_corners_win(card: list, called: set) -> bool:
    """True if all four corner cells are marked."""
    return all(_marked(card[c][r], called) for c, r in [(0, 0), (4, 0), (0, 4), (4, 4)])


def check_win(card: list, called: set) -> bool:
    return check_corners_win(card, called) or check_line_win(card, called)


def get_win_type(card: list, called: set) -> str:
    """Returns 'corners', 'line', or 'none'."""
    if check_corners_win(card, called):
        return "corners"
    if check_line_win(card, called):
        return "line"
    return "none"


def evaluate_player_cards(card_indices: list, called_numbers: list) -> list:
    """Return which card_indices have a valid win. Used for BINGO claim verification."""
    called_set = set(called_numbers)
    return [idx for idx in card_indices if check_win(get_card(idx), called_set)]


def evaluate_player_cards_detailed(card_indices: list, called_numbers: list) -> dict:
    """Like evaluate_player_cards, but returns {card_index: win_type} for
    every winning card instead of just a list. Needed when a player holds
    multiple cards and the UI must show WHICH card won and HOW (corners vs
    line), e.g. for AUTO mode or the BINGO claim confirmation screen."""
    called_set = set(called_numbers)
    winners = {}
    for idx in card_indices:
        win_type = get_win_type(get_card(idx), called_set)
        if win_type != "none":
            winners[idx] = win_type
    return winners


# =====================================================================
# AMHARIC NUMBER NAMES (1-75)
# =====================================================================

_ONES = {
    1: "አንድ",  2: "ሁለት",  3: "ሶስት",  4: "አራት",
    5: "አምስት", 6: "ስድስት", 7: "ሰባት",  8: "ስምንት", 9: "ዘጠኝ",
}
_TEENS = {
    10: "አስር",       11: "አስራ አንድ",  12: "አስራ ሁለት",
    13: "አስራ ሶስት",  14: "አስራ አራት",  15: "አስራ አምስት",
    16: "አስራ ስድስት", 17: "አስራ ሰባት",  18: "አስራ ስምንት",
    19: "አስራ ዘጠኝ",
}
_TENS = {
    20: "ሃያ",  30: "ሰላሳ", 40: "አርባ",
    50: "ሃምሳ", 60: "ስድሳ", 70: "ሰባ",
}


def number_to_amharic(n: int) -> str:
    if n in _ONES:
        return _ONES[n]
    if n in _TEENS:
        return _TEENS[n]
    tens, ones = (n // 10) * 10, n % 10
    if ones == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} {_ONES[ones]}"


def number_to_letter(n: int) -> str:
    for letter, low, high in COLUMNS:
        if low <= n <= high:
            return letter
    return "?"


def format_call_announcement(n: int) -> str:
    """Standard text for the 'current ball' display, e.g. 'B-12 (አስራ ሁለት)'.
    Used both as the message text and as the basis for the voice-file
    lookup key (config.AUDIO_DIR/{n}.ogg) in Phase 3."""
    return f"{number_to_letter(n)}-{n} ({number_to_amharic(n)})"


# =====================================================================
# CARD TEXT RENDERER  (wrap output in <pre> tags for alignment)
# =====================================================================

def render_card_text(card: list, called_numbers: list, marked_numbers: list = None) -> str:
    """
    Render a 5x5 bingo card as monospace text.
      Called numbers  ->  [12]
      FREE center     ->   FR
      Player-marked   ->  *12*   (cosmetic only)
      Unmarked        ->   12
    """
    called_set = set(called_numbers)
    marked_set = set(marked_numbers or [])

    header = "  ".join(f"{l:^4}" for l in LETTERS)
    divider = "─" * len(header)
    lines = [header, divider]

    for row in range(5):
        cells = []
        for col in range(5):
            v = card[col][row]
            if v == FREE_SPACE:
                cells.append(" FR ")
            elif v in called_set:
                cells.append(f"[{v:2}]")
            elif v in marked_set:
                cells.append(f"*{v:2}*")
            else:
                cells.append(f" {v:2} ")
        lines.append("  ".join(cells))

    return "\n".join(lines)


def render_card_with_label(card_index: int, card: list, called_numbers: list,
                           marked_numbers: list = None) -> str:
    """Full card block with card number label for multi-card display."""
    label = f"── Cartela #{card_index + 1} ──"
    body = render_card_text(card, called_numbers, marked_numbers)
    return f"{label}\n{body}"


def render_card_html(card: list, called_numbers: list, marked_numbers: list = None) -> str:
    """HTML version for Telegram parse_mode='HTML' messages, wrapped in
    <pre> for column alignment. Called numbers are bolded; numbers the
    player has manually tapped (marked_numbers) are additionally wrapped
    in brackets so the two states are visually distinct, matching the
    reference UI's highlighted-cell style."""
    called_set = set(called_numbers)
    marked_set = set(marked_numbers or [])

    header = "  ".join(f"<b>{l:^4}</b>" for l in LETTERS)
    lines = [header]

    for row in range(5):
        cells = []
        for col in range(5):
            v = card[col][row]
            if v == FREE_SPACE:
                cells.append(" FR ")
            elif v in called_set and v in marked_set:
                cells.append(f"[<b>{v:2}</b>]")
            elif v in called_set:
                cells.append(f" <b>{v:2}</b> ")
            else:
                cells.append(f" {v:2} ")
        lines.append("  ".join(cells))

    return "<pre>" + "\n".join(lines) + "</pre>"


def render_card_html_with_label(card_index: int, card: list, called_numbers: list,
                                 marked_numbers: list = None) -> str:
    """HTML card block with a bold card-number label, for multi-card display."""
    label = f"<b>Cartela #{card_index + 1}</b>"
    body = render_card_html(card, called_numbers, marked_numbers)
    return f"{label}\n{body}"


# =====================================================================
# NUMBER GRID RENDERER  (1-75 overview at top of game screen)
# =====================================================================

def render_number_grid(called_numbers: list) -> str:
    """Render 1-75 as a compact grid, called numbers in brackets.
    5 rows of 15, formatted for <pre> tags."""
    called_set = set(called_numbers)
    lines = []
    for row_start in range(1, 76, 15):
        cells = []
        for n in range(row_start, min(row_start + 15, 76)):
            if n in called_set:
                cells.append(f"[{n:2}]")
            else:
                cells.append(f" {n:2} ")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def render_number_grid_html(called_numbers: list) -> str:
    """HTML version of the 1-75 overview grid for Telegram parse_mode='HTML'
    messages - bolds called numbers instead of using bracket characters,
    wrapped in <pre> for column alignment."""
    called_set = set(called_numbers)
    lines = []
    for row_start in range(1, 76, 15):
        cells = []
        for n in range(row_start, min(row_start + 15, 76)):
            if n in called_set:
                cells.append(f"<b>{n:2}</b>")
            else:
                cells.append(f"{n:2}")
        lines.append(" ".join(cells))
    return "<pre>" + "\n".join(lines) + "</pre>"


# =====================================================================
# BALL SEQUENCE
# =====================================================================

def generate_call_sequence(seed: int = None) -> list:
    """Return a shuffled list of 1-75.
    Pass seed=None for true random (recommended per game)."""
    nums = list(range(1, 76))
    if seed is not None:
        random.Random(seed).shuffle(nums)
    else:
        random.shuffle(nums)
    return nums


# =====================================================================
# USERNAME MASKING
# =====================================================================

def mask_username(username: str, visible: int = 3) -> str:
    """e.g. 'fUCijZmjgEq' -> '@fUC***'"""
    if not username:
        return "@***"
    username = username.lstrip("@")
    return f"@{username[:visible]}***"


# =====================================================================
# SELF-TEST  (python3 bingo.py)
# =====================================================================
if __name__ == "__main__":
    print("=== Card pool ===")
    pool = generate_card_pool(200)
    fps = {tuple(sorted(n for col in c for n in col if n != FREE_SPACE)) for c in pool}
    print(f"200 cards, {len(fps)} unique fingerprints")

    card = pool[0]
    print("\nCard #1:")
    print(render_card_text(card, []))

    corners_vals = [card[0][0], card[4][0], card[0][4], card[4][4]]
    called = set(corners_vals)
    print(f"\nCorners called {corners_vals}:")
    print(f"  corners={check_corners_win(card, called)} line={check_line_win(card, called)} type={get_win_type(card, called)}")

    col0 = [card[0][r] for r in range(5)]
    print(f"\nColumn-0 called {col0}:")
    print(f"  line={check_line_win(card, set(col0))}")

    print("\n=== Amharic ===")
    for n in [1, 9, 10, 13, 19, 20, 21, 30, 45, 60, 74, 75]:
        print(f"  {n:2} = {number_to_amharic(n)}")

    print("\n=== Number grid ===")
    sample_called = [3, 16, 31, 46, 61, 7, 22, 38, 55, 70]
    print(render_number_grid(sample_called))

    print("\n=== Card with called numbers ===")
    print(render_card_text(pool[1], sample_called, marked_numbers=[pool[1][0][0]]))

    print("\n=== Masking ===")
    for name in ["fUCijZmjgEq", "Ab8xyz", "Al", "Yidnekachew"]:
        print(f"  {name} -> {mask_username(name)}")

    print("\n=== Multi-card detailed evaluation ===")
    # Give player cards 0 and 1; rig called numbers so card 0 gets corners
    # and card 1 gets nothing, to confirm per-card win typing works.
    card0_corners = [pool[0][0][0], pool[0][4][0], pool[0][0][4], pool[0][4][4]]
    detailed = evaluate_player_cards_detailed([0, 1], card0_corners)
    print(f"  Called: {card0_corners}")
    print(f"  Detailed result: {detailed}  (expect {{0: 'corners'}})")

    print("\n=== HTML rendering ===")
    print(render_card_html(pool[0], sample_called))
    print()
    print(render_card_html_with_label(0, pool[0], sample_called, marked_numbers=[pool[0][0][0]]))
    print()
    print(render_number_grid_html(sample_called))

    print("\n=== Call announcement ===")
    for n in [7, 12, 38, 61]:
        print(f"  {format_call_announcement(n)}")
