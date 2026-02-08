"""
Logger utility for FPVCopilotSky
"""

import logging
import sys


def get_logger(name: str = None) -> logging.Logger:
    """Get a configured logger instance"""
    logger = logging.getLogger(name or "fpvcopilot")

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


# Default logger instance
logger = get_logger()
