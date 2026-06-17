"""
bingo.py — Card generation, win checking, Amharic number names, rendering.
"""

import random
from typing import Optional


# ── Amharic number names 1-75 ──────────────────────────────────────────────────
AMHARIC: dict[int, str] = {
    1: "አንድ", 2: "ሁለት", 3: "ሦስት", 4: "አራት", 5: "አምስት",
    6: "ስድስት", 7: "ሰባት", 8: "ስምንት", 9: "ዘጠኝ", 10: "አስር",
    11: "አስራ አንድ", 12: "አስራ ሁለት", 13: "አስራ ሦስት", 14: "አስራ አራት",
    15: "አስራ አምስት", 16: "አስራ ስድስት", 17: "አስራ ሰባት", 18: "አስራ ስምንት",
    19: "አስራ ዘጠኝ", 20: "ሃያ", 21: "ሃያ አንድ", 22: "ሃያ ሁለት",
    23: "ሃያ ሦስት", 24: "ሃያ አራት", 25: "ሃያ አምስት", 26: "ሃያ ስድስት",
    27: "ሃያ ሰባት", 28: "ሃያ ስምንት", 29: "ሃያ ዘጠኝ", 30: "ሠላሳ",
    31: "ሠላሳ አንድ", 32: "ሠላሳ ሁለት", 33: "ሠላሳ ሦስት", 34: "ሠላሳ አራት",
    35: "ሠላሳ አምስት", 36: "ሠላሳ ስድስት", 37: "ሠላሳ ሰባት", 38: "ሠላሳ ስምንት",
    39: "ሠላሳ ዘጠኝ", 40: "አርባ", 41: "አርባ አንድ", 42: "አርባ ሁለት",
    43: "አርባ ሦስት", 44: "አርባ አራት", 45: "አርባ አምስት", 46: "አርባ ስድስት",
    47: "አርባ ሰባት", 48: "አርባ ስምንት", 49: "አርባ ዘጠኝ", 50: "ሃምሳ",
    51: "ሃምሳ አንድ", 52: "ሃምሳ ሁለት", 53: "ሃምሳ ሦስት", 54: "ሃምሳ አራት",
    55: "ሃምሳ አምስት", 56: "ሃምሳ ስድስት", 57: "ሃምሳ ሰባት", 58: "ሃምሳ ስምንት",
    59: "ሃምሳ ዘጠኝ", 60: "ስልሳ", 61: "ስልሳ አንድ", 62: "ስልሳ ሁለት",
    63: "ስልሳ ሦስት", 64: "ስልሳ አራት", 65: "ስልሳ አምስት", 66: "ስልሳ ስድስት",
    67: "ስልሳ ሰባት", 68: "ስልሳ ስምንት", 69: "ስልሳ ዘጠኝ", 70: "ሰባ",
    71: "ሰባ አንድ", 72: "ሰባ ሁለት", 73: "ሰባ ሦስት", 74: "ሰባ አራት",
    75: "ሰባ አምስት",
}


def to_amharic(n: int) -> str:
    """Convert integer 1-75 to its Amharic word."""
    return AMHARIC.get(n, str(n))


# ── Card generation ────────────────────────────────────────────────────────────

# Standard Bingo column ranges
_COLUMN_RANGES = [
    (1, 15),   # B
    (16, 30),  # I
    (31, 45),  # N
    (46, 60),  # G
    (61, 75),  # O
]


def _make_card(rng: random.Random) -> list[list[int]]:
    """
    Generate a single 5×5 Bingo card.
    Grid[row][col].  Center (row=2, col=2) = 0 (FREE space).
    """
    columns: list[list[int]] = []
    for low, high in _COLUMN_RANGES:
        nums = sorted(rng.sample(range(low, high + 1), 5))
        columns.append(nums)

    # Transpose: grid[row][col]
    grid = [[columns[col][row] for col in range(5)] for row in range(5)]
    grid[2][2] = 0  # FREE
    return grid


def generate_unique_cards(count: int, seed: int) -> list[list[list[int]]]:
    """
    Generate `count` unique Bingo cards using a fixed `seed` for reproducibility.
    Raises ValueError if it's impossible to generate that many unique cards.
    """
    rng = random.Random(seed)
    cards: list[list[list[int]]] = []
    seen: set[tuple] = set()
    attempts = 0
    max_attempts = count * 200

    while len(cards) < count and attempts < max_attempts:
        attempts += 1
        grid = _make_card(rng)
        key = tuple(n for row in grid for n in row)
        if key not in seen:
            seen.add(key)
            cards.append(grid)

    if len(cards) < count:
        raise ValueError(f"Could only generate {len(cards)} unique cards (wanted {count})")

    return cards


# ── Win checking ───────────────────────────────────────────────────────────────

def check_win(
    grid: list[list[int]],
    called: set[int],
) -> tuple[bool, Optional[str]]:
    """
    Check whether a card has a winning pattern against the called numbers.
    Win types: 'line' (row, col, diagonal) or 'corners' (4 corners).
    Full House is intentionally NOT checked.

    Returns (has_won: bool, win_type: str | None).
    """
    # A cell is marked if it's FREE (0) or its number was called
    marked = [[n == 0 or n in called for n in row] for row in grid]

    # ── Rows ──────────────────────────────────────────────────────────────────
    for row in marked:
        if all(row):
            return True, "line"

    # ── Columns ───────────────────────────────────────────────────────────────
    for col in range(5):
        if all(marked[row][col] for row in range(5)):
            return True, "line"

    # ── Main diagonal (top-left → bottom-right) ───────────────────────────────
    if all(marked[i][i] for i in range(5)):
        return True, "line"

    # ── Anti-diagonal (top-right → bottom-left) ───────────────────────────────
    if all(marked[i][4 - i] for i in range(5)):
        return True, "line"

    # ── Four corners ──────────────────────────────────────────────────────────
    if (marked[0][0] and marked[0][4] and
            marked[4][0] and marked[4][4]):
        return True, "corners"

    return False, None


# ── Text rendering ─────────────────────────────────────────────────────────────

def render_card_text(
    grid: list[list[int]],
    called: set[int],
    card_num: int,
) -> str:
    """
    Render a Bingo card as HTML-formatted monospace text.
    Called numbers are shown in bold; FREE space shown as ★.
    """
    lines = [f"<b>Card #{card_num}</b>", "<code> B   I   N   G   O"]
    for row in grid:
        cells = []
        for num in row:
            if num == 0:
                cells.append(" ★ ")
            elif num in called:
                cells.append(f"[{num:2d}]")
            else:
                cells.append(f" {num:2d} ")
        lines.append("".join(cells))
    lines.append("</code>")
    return "\n".join(lines)


def render_number_grid(called: list[int]) -> str:
    """
    Render the 1-75 master grid as compact HTML.
    Called numbers are shown in bold brackets.
    Returns a <code>…</code> block (15 per row).
    """
    called_set = set(called)
    cells = []
    for n in range(1, 76):
        if n in called_set:
            cells.append(f"[{n:2d}]")
        else:
            cells.append(f" {n:2d} ")

    rows = [cells[i: i + 15] for i in range(0, 75, 15)]
    body = "\n".join("".join(r) for r in rows)
    return f"<code>{body}</code>"
