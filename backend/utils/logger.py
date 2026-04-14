import sys
from loguru import logger
from backend.config import settings


def setup_logger() -> None:
    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        colorize=True,
    )

    logger.add(
        "logs/agent.log",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
        rotation="10 MB",
        retention="14 days",
        compression="zip",
    )


setup_logger()

__all__ = ["logger"]
