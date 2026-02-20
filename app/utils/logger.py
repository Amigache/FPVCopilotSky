"""
Logger utility for FPVCopilotSky
"""

import logging
import sys


def get_logger(name: str = None, fmt: str = None) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (defaults to 'fpvcopilot').
        fmt:  Log format string.  Defaults to the standard timestamped format.
              Pass ``"%(message)s"`` to emit the bare message (useful when
              the surrounding log infrastructure — e.g. journald — already
              adds timestamp and source information).
    """
    logger = logging.getLogger(name or "fpvcopilot")

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


# Default logger instance
logger = get_logger()
