"""
sms_parser.py — Robust Telebirr SMS parser and recipient verifier.

Example SMS:
  Dear Customer, you have transferred ETB 20.00 to Habesha Bet
  13/06/2026 19:22:57. Your transaction number is DFF3WS88X9.
  The service fee is ETB 0.87 and 15% VAT on the service fee is ETB 0.13.
  Your current E-Money Account balance is ETB 1,017.52.
  Thank you for using telebirr Ethio telecom
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TelebirrSMS:
    amount: float
    reference: str
    recipient: str           # name or phone extracted from SMS
    raw: str


# ── Regex patterns ─────────────────────────────────────────────────────────────

# Amount: "transferred ETB 20.00" or "ETB 20.00 to"
_AMOUNT_RE = re.compile(
    r"transferred\s+ETB\s+([\d,]+(?:\.\d+)?)",
    re.IGNORECASE
)

# Reference: "transaction number is DFF3WS88X9"
_REF_RE = re.compile(
    r"transaction\s+(?:number|id|reference)\s+is\s+([A-Z0-9]+)",
    re.IGNORECASE
)

# Recipient name: "transferred ETB 20.00 to <name>"
_RECIPIENT_NAME_RE = re.compile(
    r"transferred\s+ETB\s+[\d,]+(?:\.\d+)?\s+to\s+([A-Za-z\s]+?)(?:\s+\d{2}/\d{2}/\d{4}|\s+on\s+|\s+\d+/|\.|$)",
    re.IGNORECASE
)

# Recipient phone (if SMS contains phone instead of name)
_RECIPIENT_PHONE_RE = re.compile(
    r"to\s+(09\d{8})",
    re.IGNORECASE
)


def parse_telebirr_sms(sms_text: str) -> Optional[TelebirrSMS]:
    """
    Parse a Telebirr confirmation SMS.
    Returns TelebirrSMS on success, None if parsing fails.
    """
    text = sms_text.strip()

    # Extract amount
    m_amount = _AMOUNT_RE.search(text)
    if not m_amount:
        return None
    try:
        amount = float(m_amount.group(1).replace(",", ""))
    except ValueError:
        return None

    # Extract reference
    m_ref = _REF_RE.search(text)
    if not m_ref:
        return None
    reference = m_ref.group(1).strip().upper()

    # Extract recipient (name preferred, phone fallback)
    recipient = ""
    m_name = _RECIPIENT_NAME_RE.search(text)
    if m_name:
        recipient = m_name.group(1).strip()
    else:
        m_phone = _RECIPIENT_PHONE_RE.search(text)
        if m_phone:
            recipient = m_phone.group(1).strip()

    return TelebirrSMS(
        amount=amount,
        reference=reference,
        recipient=recipient,
        raw=text,
    )


def verify_recipient(
    sms: TelebirrSMS,
    accepted_names: list[str],
    accepted_phone_last4: list[str],
) -> bool:
    """
    Verify that the SMS recipient matches expected name fragments OR phone last-4 digits.
    Case-insensitive partial match on names.
    """
    recipient_lower = sms.recipient.lower().strip()

    # Check name fragments
    for name_frag in accepted_names:
        if name_frag.lower() in recipient_lower:
            return True

    # Check last-4 digits of phone
    digits_only = re.sub(r"\D", "", sms.recipient)
    for last4 in accepted_phone_last4:
        if digits_only.endswith(last4):
            return True

    return False


def verify_amount(sms: TelebirrSMS, expected_amount: float) -> bool:
    """Check that SMS amount matches the requested deposit amount."""
    return abs(sms.amount - expected_amount) < 0.01
