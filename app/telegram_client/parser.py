import re
from typing import Optional, List, Tuple
from urllib.parse import urlparse


def normalize_channel_input(raw_input: str) -> str:
    """Normalizes various forms of Telegram channel links or usernames into a clean identifier.

    Examples:
    - https://t.me/mychannel -> mychannel
    - https://t.me/s/mychannel -> mychannel
    - https://t.me/mychannel/ -> mychannel
    - https://t.me/mychannel?start=123 -> mychannel
    - @mychannel -> mychannel
    - mychannel -> mychannel
    - +AbCdEf123... (private invite link hash) -> +AbCdEf123...
    - https://t.me/+AbCdEf123 -> +AbCdEf123
    - https://t.me/joinchat/AbCdEf123 -> +AbCdEf123
    """
    cleaned = raw_input.strip()
    if not cleaned:
        return ""

    # Remove query string / fragment if present
    if "?" in cleaned:
        cleaned = cleaned.split("?")[0]
    if "#" in cleaned:
        cleaned = cleaned.split("#")[0]

    # Handle web links
    if "t.me/" in cleaned or "telegram.me/" in cleaned:
        parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        if not path_parts:
            return ""

        # Handle https://t.me/s/channel
        if path_parts[0] == "s" and len(path_parts) > 1:
            return path_parts[1].lstrip("@")

        # Handle joinchat
        if path_parts[0] == "joinchat" and len(path_parts) > 1:
            return f"+{path_parts[1]}"

        # Handle https://t.me/+hash
        if path_parts[0].startswith("+"):
            return path_parts[0]

        return path_parts[0].lstrip("@")

    # If it's @channel
    if cleaned.startswith("@"):
        return cleaned.lstrip("@")

    return cleaned


def is_ad_message(
    text: Optional[str],
    entities: Optional[List[any]] = None,
    keywords: Optional[List[str]] = None,
) -> bool:
    """Checks whether a message matches any of the target advertising keywords.
    Matches are case-insensitive and check:
    1. Direct message text / caption.
    2. Entity text_link URLs (e.g. [Bog'lanish](https://t.me/imkonhelpbot)).
    3. Entity mentions or plain URLs.
    """
    if not keywords:
        keywords = ["@imkonhelpbot"]

    normalized_keywords = [k.strip().lower() for k in keywords if k.strip()]
    if not normalized_keywords:
        normalized_keywords = ["@imkonhelpbot"]

    # 1. Check plain text
    if text:
        text_lower = text.lower()
        for kw in normalized_keywords:
            # Check for direct keyword, e.g. @imkonhelpbot
            if kw in text_lower:
                return True
            # Also check if username without @ appears in link form, e.g. t.me/imkonhelpbot
            kw_clean = kw.lstrip("@")
            if f"t.me/{kw_clean}" in text_lower or f"telegram.me/{kw_clean}" in text_lower:
                return True

    # 2. Check entities (MessageEntityTextUrl, etc.)
    if entities and text:
        for ent in entities:
            # Telethon entity types or dict/mock
            url = getattr(ent, "url", None)
            if not url and isinstance(ent, dict):
                url = ent.get("url")

            if url:
                url_lower = url.lower()
                for kw in normalized_keywords:
                    kw_clean = kw.lstrip("@")
                    if kw in url_lower or kw_clean in url_lower:
                        return True

            # Check entity slice in text
            offset = getattr(ent, "offset", None)
            length = getattr(ent, "length", None)
            if offset is not None and length is not None:
                snippet = text[offset : offset + length].lower()
                for kw in normalized_keywords:
                    if kw in snippet:
                        return True

    return False


def build_post_url(
    channel_id: int,
    username: Optional[str],
    message_id: int,
) -> str:
    """Builds a canonical public or private Telegram post URL."""
    if username:
        clean_user = username.lstrip("@")
        return f"https://t.me/{clean_user}/{message_id}"

    # For private channels, channel_id is usually -1001234567890
    cid_str = str(channel_id)
    if cid_str.startswith("-100"):
        cid_str = cid_str[4:]
    elif cid_str.startswith("-"):
        cid_str = cid_str[1:]

    return f"https://t.me/c/{cid_str}/{message_id}"


def extract_media_type(message: any) -> Optional[str]:
    """Determines the media type of a Telethon message."""
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "gif", None):
        return "animation"
    if getattr(message, "text", None):
        return "text"
    return "other"


def extract_reactions_count(message: any) -> Optional[int]:
    """Extracts total reactions count from a Telethon message if available."""
    reactions = getattr(message, "reactions", None)
    if not reactions:
        return None

    results = getattr(reactions, "results", None)
    if not results:
        return None

    total = 0
    for res in results:
        count = getattr(res, "count", 0)
        total += count
    return total
