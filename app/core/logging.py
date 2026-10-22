import logging
import sys
import re
from app.core.config import settings


def redact_sensitive(text: str) -> str:
    # Exact configured values also cover session/token formats outside our patterns.
    for value in (settings.BOT_TOKEN, settings.TELEGRAM_API_HASH,
                  settings.TELEGRAM_SESSION_STRING, settings.DATABASE_URL):
        if value and len(value) >= 8:
            text = text.replace(value, "[REDACTED_SECRET]")
    for pattern in SensitiveFilter.SENSITIVE_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    return text


class SensitiveFilter(logging.Filter):
    """Filters out sensitive information from logs such as bot tokens, api hash, session strings."""

    SENSITIVE_PATTERNS = [
        re.compile(r"(?:bot)?[0-9]{6,16}:[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
        re.compile(r"([0-9a-f]{32})", re.IGNORECASE),  # API HASH length
        re.compile(r"1[A-Za-z0-9_=-]{100,}"),  # Telethon session strings
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.getMessage())
        record.args = ()
        return True


class SensitiveFormatter(logging.Formatter):
    def formatException(self, exc_info) -> str:
        return redact_sensitive(super().formatException(exc_info))

    def format(self, record) -> str:
        # Also protect cached exception text and stack_info produced by other handlers.
        return redact_sensitive(super().format(record))


def setup_logging(level: str = "INFO") -> None:
    """Configures structured logging for the application."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    while root_logger.handlers:
        root_logger.removeHandler(root_logger.handlers[0])

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    formatter = SensitiveFormatter(fmt=log_format, datefmt=date_format)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SensitiveFilter())

    root_logger.addHandler(console_handler)

    # Silence overly verbose external loggers
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


logger = logging.getLogger("imkon_ads_monitor")
