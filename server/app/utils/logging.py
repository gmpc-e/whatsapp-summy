import logging, os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.config import settings

def configure_logging():
    log_level = logging.DEBUG if settings.DEBUG or settings.LOG_LEVEL.upper()=="DEBUG" else getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # root console
    logging.basicConfig(level=log_level, format=fmt, datefmt=datefmt)

    # rotating file
    Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(settings.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(logging.Formatter(fmt, datefmt))
    logging.getLogger().addHandler(fh)

    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("uvicorn.error").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(log_level)
