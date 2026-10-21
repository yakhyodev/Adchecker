import html
import re
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    VIEWER = "viewer"


def sanitize_excel_cell(val: any) -> any:
    """Prevents CSV/Excel formula injection by escaping dangerous leading characters.
    Characters: '=', '+', '-', '@', '\t', '\r'
    """
    if val is None:
        return ""
    if not isinstance(val, str):
        return val

    # If it starts with formula trigger characters, prefix with single quote
    dangerous_prefixes = ("=", "+", "-", "@", "\t", "\r", "%")
    if val.startswith(dangerous_prefixes):
        return "'" + val
    return val


def escape_tg_html(text: Optional[str]) -> str:
    """Escapes HTML special characters for safe sending in Telegram HTML parse mode."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def truncate_message(text: str, max_length: int = 4000) -> str:
    """Truncates text to Telegram message length limits."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
