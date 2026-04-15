import os
import sys
from loguru import logger
from backend.config import settings

_FMT_COLOUR = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
    "<level>{message}</level>"
)
_FMT_PLAIN = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}"


def setup_logger() -> None:
    logger.remove()

    # Always log to stdout (Render / any host captures this natively)
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=_FMT_COLOUR,
        colorize=True,
    )

    # File logging only when running locally (LOG_FILE env var or not on Render)
    log_file = os.environ.get("LOG_FILE")
    if log_file:
        logger.add(
            log_file,
            level=settings.log_level,
            format=_FMT_PLAIN,
            rotation="10 MB",
            retention="14 days",
            compression="zip",
        )


setup_logger()

__all__ = ["logger"]
