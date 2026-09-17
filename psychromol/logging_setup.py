
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import Settings

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-8s %(name)-28s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

def configure_logging(settings: Settings) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.log_file:
        path = Path(settings.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)
    for handler in handlers:
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    for handler in handlers:
        root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True
