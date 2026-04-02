from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict


_LOGGER_NAME = "circadian_app"
_REDACT_PATTERNS = [
    re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b"),
    re.compile(r"\b\d{2,4}[-/ ]?\d{2,4}[-/ ]?\d{2,4}\b"),
]


def redact_text(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pattern in _REDACT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str):
            out[k] = redact_text(v)
        else:
            out[k] = v
    return out


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def log_event(event: str, **kwargs: Any) -> None:
    logger = get_logger()
    payload = {"event": event, **redact_payload(kwargs)}
    logger.info(json.dumps(payload, default=str))
