"""
Structured logging configuration.

Sets up JSON-formatted logging for production and human-readable
formatting for development (DEBUG=True).

Usage:
    from app.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("Document ingested", extra={"doc_id": str(doc.id), "chunks": 42})
"""
import logging
import sys
from app.config import get_settings

settings = get_settings()


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter — one log line per record."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, val in record.__dict__.items():
            if key not in {
                "msg", "args", "levelname", "levelno", "name", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                payload[key] = val
        return json.dumps(payload)


def configure_logging() -> None:
    """Call once at application startup."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if settings.DEBUG:
        fmt = logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
    else:
        handler.setFormatter(_JsonFormatter())

    # Remove any existing handlers (e.g. uvicorn's default)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
