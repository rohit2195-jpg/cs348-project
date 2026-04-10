"""
validation.py — centralized request/input validation helpers
Used by the Flask API and trading layer so all user-controlled inputs
follow the same normalization and allowlist rules.
"""

from __future__ import annotations

import re
from datetime import datetime


SYMBOL_MAX_LEN = 10
WATCHLIST_NOTES_MAX_LEN = 500

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,9}$")
_ALPACA_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class ValidationError(ValueError):
    """Raised when user-controlled input fails validation."""


def normalize_symbol(value) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        raise ValidationError("symbol is required")
    if len(symbol) > SYMBOL_MAX_LEN or not _SYMBOL_RE.fullmatch(symbol):
        raise ValidationError(
            f"Invalid symbol '{symbol}'. Symbols may contain letters, digits, '.' or '-', "
            f"up to {SYMBOL_MAX_LEN} characters."
        )
    return symbol


def parse_symbol_list(value) -> list[str]:
    if not value:
        return []
    symbols = []
    seen = set()
    for raw in str(value).split(","):
        raw = raw.strip()
        if not raw:
            continue
        symbol = normalize_symbol(raw)
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def parse_positive_int(value, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a positive integer")
    if parsed <= 0:
        raise ValidationError(f"{field_name} must be a positive integer")
    return parsed


def parse_optional_float(value, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a number")


def parse_enum(value, allowed_values: set[str], field_name: str) -> str | None:
    if value in (None, ""):
        return None
    parsed = str(value).strip().lower()
    if parsed not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise ValidationError(f"{field_name} must be one of: {allowed}")
    return parsed


def parse_date_string(value, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    parsed = str(value).strip()
    try:
        datetime.strptime(parsed, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"{field_name} must be in YYYY-MM-DD format")
    return parsed


def validate_notes(value) -> str | None:
    if value is None:
        return None
    notes = str(value).strip()
    if len(notes) > WATCHLIST_NOTES_MAX_LEN:
        raise ValidationError(f"notes must be {WATCHLIST_NOTES_MAX_LEN} characters or fewer")
    return notes


def parse_alpaca_order_id(value) -> str:
    alpaca_id = str(value or "").strip()
    if not alpaca_id:
        raise ValidationError("alpaca_order_id is required")
    if not _ALPACA_ID_RE.fullmatch(alpaca_id):
        raise ValidationError("alpaca_order_id has an invalid format")
    return alpaca_id

