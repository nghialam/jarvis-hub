"""
core/logging_config.py - Structured logging with rotation for Jarvis Hub 3.0

Replaces all print() statements in production code.
Log rotation: 10MB max, 5 backup files.
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Directory for logs
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Log file paths
LOG_FILE = os.path.join(LOG_DIR, "jarvis_hub.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "jarvis_hub_error.log")


def setup_logging(log_level="INFO", log_file=None):
    """
    Configure structured logging for the entire application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Custom log file path (uses default if None)
    
    Returns:
        logger: Configured root logger
    """
    if log_file is None:
        log_file = LOG_FILE

    # Formatter with timestamp, level, name, message
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # File handler with rotation (10MB, 5 backups)
    try:
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[LOGGING] Failed to create file handler: {e}")

    # Error file handler (all errors and above)
    try:
        error_handler = RotatingFileHandler(
            filename=ERROR_LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        logger.addHandler(error_handler)
    except Exception as e:
        print(f"[LOGGING] Failed to create error file handler: {e}")

    return logger


def get_logger(name):
    """Get a named logger instance."""
    return logging.getLogger(name)


def log(module_name, level, message, **kwargs):
    """Convenience function for structured logging."""
    logger = get_logger(module_name)
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=kwargs if kwargs else None)


# Pre-configured loggers for major modules
LOG = {
    "APP": lambda level, msg: log("APP", level, msg),
    "CFG": lambda level, msg: log("CFG", level, msg),
    "DB": lambda level, msg: log("DB", level, msg),
    "REFRESH": lambda level, msg: log("REFRESH", level, msg),
    "SCHEDULER": lambda level, msg: log("SCHEDULER", level, msg),
    "KB": lambda level, msg: log("KB", level, msg),
    "QUOTES": lambda level, msg: log("QUOTES", level, msg),
    "BACKLOG": lambda level, msg: log("BACKLOG", level, msg),
    "ALERTS": lambda level, msg: log("ALERTS", level, msg),
    "ANALYZE": lambda level, msg: log("ANALYZE", level, msg),
    "ARTICLES": lambda level, msg: log("ARTICLES", level, msg),
    "EVAL": lambda level, msg: log("EVAL", level, msg),
    "INDICES": lambda level, msg: log("INDICES", level, msg),
    "SIGNALS": lambda level, msg: log("SIGNALS", level, msg),
    "ALERT": lambda level, msg: log("ALERT", level, msg),
    "AUTO_SCAN": lambda level, msg: log("AUTO_SCAN", level, msg),
    "NEWS": lambda level, msg: log("NEWS", level, msg),
    "SCORE": lambda level, msg: log("SCORE", level, msg),
    "MI": lambda level, msg: log("MI", level, msg),
    "CMS": lambda level, msg: log("CMS", level, msg),
    "FALLBACK": lambda level, msg: log("FALLBACK", level, msg),
    "HEALTH": lambda level, msg: log("HEALTH", level, msg),
    "TELEGRAM": lambda level, msg: log("TELEGRAM", level, msg),
    "DASHBOARD": lambda level, msg: log("DASHBOARD", level, msg),
}
