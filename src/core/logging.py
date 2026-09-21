"""Structured logging with ``run_id`` and ``stage`` bound to context.

One JSON object per line, so a run's log is queryable after the fact rather than
only readable. This matters for two specification requirements: spec Section 29.14
requires invalid inputs and model failures to be logged, and spec Section 28
requires diagnosing an unexpected case count by stage — both of which mean
filtering a log by stage and reason, not scrolling it.

``run_id`` and ``stage`` travel in ``contextvars`` rather than being passed to
every call, so a helper deep in a stage does not need a logger argument threaded
through five frames to produce an attributable line.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Final, Iterator, TextIO

_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "run_id", default=None
)
_stage: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "stage", default=None
)

LOGGER_NAMESPACE: Final[str] = "engine"

#: Attributes ``logging`` puts on every record. Anything outside this set was
#: supplied by the caller via ``extra=`` and is merged into the JSON payload.
_STANDARD_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        run_id, stage = _run_id.get(), _stage.get()
        if run_id is not None:
            payload["run_id"] = run_id
        if stage is not None:
            payload["stage"] = stage

        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    level: int | str = logging.INFO, stream: TextIO | None = None
) -> logging.Logger:
    """Configure the ``engine`` logger. Idempotent.

    Attaches to the ``engine`` namespace rather than the root logger, so enabling
    debug output here does not also enable it for every installed library.
    ``propagate`` is off to avoid duplicate lines when a host application has
    already configured the root logger — Streamlit does.
    """
    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.setLevel(level)
    logger.propagate = False

    for existing in list(logger.handlers):
        logger.removeHandler(existing)

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger inside the ``engine`` namespace."""
    return logging.getLogger(
        LOGGER_NAMESPACE if not name else f"{LOGGER_NAMESPACE}.{name}"
    )


@contextmanager
def bind_context(
    *, run_id: str | None = None, stage: str | None = None
) -> Iterator[None]:
    """Bind ``run_id`` and/or ``stage`` for the duration of the block.

    Restores the previous values on exit, including when the block raises, so a
    failing stage cannot leak its name into subsequent log lines.
    """
    tokens: list[tuple[contextvars.ContextVar[str | None], Any]] = []
    if run_id is not None:
        tokens.append((_run_id, _run_id.set(run_id)))
    if stage is not None:
        tokens.append((_stage, _stage.set(stage)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def current_context() -> dict[str, str | None]:
    """The bound context, for inclusion in a manifest or an error report."""
    return {"run_id": _run_id.get(), "stage": _stage.get()}
