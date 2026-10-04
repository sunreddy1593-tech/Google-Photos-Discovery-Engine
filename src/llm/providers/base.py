"""Provider protocol and the errors the gateway knows how to record.

Nothing in this module imports a vendor SDK. Adapters translate vendor
exceptions into :class:`ProviderCallError` so the rest of the pipeline never
sees a vendor type.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Protocol

if TYPE_CHECKING:
    from pydantic import BaseModel

from src.core.errors import ProviderError
from src.models.enums import DecisionTechnicalState

_CLASS_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")
_ERROR_TYPE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_ERROR_PARAM = re.compile(r"^[A-Za-z0-9_./\[\]-]{1,160}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,128}$")
_SECRET_PREFIXES = ("gsk-", "sk-")
_BEARER = re.compile(
    r"(?i)\b((?:authorization\s*:\s*)?bearer\s+)[A-Za-z0-9._\-]{8,}"
)
_KEY = re.compile(r"(?i)\b(?:gsk-|sk-)[A-Za-z0-9_\-]{4,}")
_MESSAGE_LIMIT = 400
_ERROR_FIELDS = ("message", "type", "code", "param")
_REQUEST_HEADERS = ("x-request-id", "request-id", "x-groq-request-id")
_FINISH_REASONS = frozenset({"stop", "length", "tool_calls", "function_call"})
_INSPECTION_LIMIT = 65_536
_DIAGNOSTIC_CATEGORIES = frozenset(
    {
        "authentication",
        "permission_denied",
        "not_found",
        "invalid_request",
        "unprocessable",
        "conflict",
        "rate_limited",
        "timeout",
        "connection",
        "server_error",
        "http_status",
        "sdk_error",
        "local_exception",
    }
)


@dataclass(frozen=True)
class ProviderDiagnostic:
    """Allowlisted provider failure details. The message is sanitized and bounded."""

    category: str
    sdk_exception_class: str | None = None
    http_status: int | None = None
    provider_error_type: str | None = None
    request_id: str | None = None
    error_code: str | None = None
    error_param: str | None = None
    error_message: str | None = None
    rejected_output_summary: dict[str, object] | None = None
    finish_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "sdk_exception_class": self.sdk_exception_class,
            "http_status": self.http_status,
            "provider_error_type": self.provider_error_type,
            "request_id": self.request_id,
            "error_code": self.error_code,
            "error_param": self.error_param,
            "error_message": self.error_message,
            "rejected_output_summary": self.rejected_output_summary,
            "finish_reason": self.finish_reason,
        }


def diagnostic_from_exception(
    exc: BaseException,
    *,
    category: str,
    redact: tuple[str, ...] = (),
    response_model: type[BaseModel] | None = None,
) -> ProviderDiagnostic:
    """Keep status, type, code, param, and a sanitized message."""
    status = _http_status(exc)
    code, param, message = _error_details(getattr(exc, "body", None), redact)
    error = _error_object(getattr(exc, "body", None))
    return ProviderDiagnostic(
        category=category if category in _DIAGNOSTIC_CATEGORIES else "sdk_error",
        sdk_exception_class=_class_name(type(exc).__name__),
        http_status=status,
        provider_error_type=_error_type(getattr(exc, "body", None)),
        request_id=_request_id(getattr(exc, "response", None)),
        error_code=code,
        error_param=param,
        error_message=message,
        rejected_output_summary=None if error is None else _rejected_output_summary(error, response_model),
        finish_reason=None if error is None else safe_finish_reason(error.get("finish_reason")),
    )


def safe_finish_reason(value: object) -> str | None:
    """Only known SDK finish reasons, never free-form provider text."""
    return value if isinstance(value, str) and value in _FINISH_REASONS else None


def _rejected_output_summary(
    error: dict[str, object], response_model: type[BaseModel] | None,
) -> dict[str, object] | None:
    """Inspect transient generated text; retain no text, values or error messages.

    Application validation is diagnostic only. It neither replaces the vendor's
    strict-schema check nor accepts the rejected response as a completion.
    """
    if "failed_generation" not in error:
        return None
    raw = error["failed_generation"]
    summary: dict[str, object] = {"json_state": "not_text", "application_state": "not_checked"}
    if not isinstance(raw, str):
        return summary
    summary["character_count"] = len(raw)
    if len(raw) > _INSPECTION_LIMIT:
        summary["json_state"] = "oversized"
        return summary
    if not raw.strip():
        summary["json_state"] = "empty"
        return summary
    try:
        def reject_constant(value: str) -> None:
            raise ValueError("non-JSON numeric constant")

        payload = json.loads(raw, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        summary.update(json_state="invalid_json", json_error_position=exc.pos)
        return summary
    except ValueError:
        summary["json_state"] = "invalid_json"
        return summary
    except RecursionError:
        summary["json_state"] = "inspection_failed"
        return summary
    summary["json_state"] = "valid_json"
    if response_model is None:
        return summary
    from pydantic import ValidationError

    try:
        response_model.model_validate(payload)
    except ValidationError as exc:
        # Locations can contain invented extra keys or union labels. Only names
        # from the application's fixed schema may leave this transient check.
        names: set[str] = set()

        def schema_names(node: object) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    names.update(name for name in properties if isinstance(name, str) and len(name) <= 64)
                for child in node.values():
                    schema_names(child)
            elif isinstance(node, list):
                for child in node:
                    schema_names(child)

        schema_names(response_model.model_json_schema())
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        summary.update(
            application_state="invalid",
            validation_error_count=len(errors),
            validation_errors=[
                {
                    "type": _bounded_token(finding["type"], _ERROR_TYPE) or "validation_error",
                    "path": [
                        part if (type(part) is int or isinstance(part, str) and part in names) else "*"
                        for part in finding["loc"][:16]
                    ],
                }
                for finding in errors[:32]
            ],
        )
    except (ValueError, TypeError, RecursionError):
        summary["application_state"] = "inspection_failed"
    else:
        summary["application_state"] = "valid"
    return summary


def _http_status(exc: BaseException) -> int | None:
    raw = getattr(exc, "status_code", None)
    if isinstance(raw, int) and 100 <= raw <= 599:
        return raw
    return None


def _class_name(name: str) -> str | None:
    if _CLASS_NAME.fullmatch(name):
        return name
    return None


def _error_object(body: object) -> dict[str, object] | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    return error


def _error_type(body: object) -> str | None:
    error = _error_object(body)
    if error is None:
        return None
    return _bounded_token(error.get("type"), _ERROR_TYPE)


def _error_details(
    body: object,
    redact: tuple[str, ...],
) -> tuple[str | None, str | None, str | None]:
    """Read code, param, and message. Ignore generated-content fields."""
    error = _error_object(body)
    if error is None:
        return None, None, None
    generated = tuple(
        value
        for key, value in error.items()
        if key not in _ERROR_FIELDS and isinstance(value, str)
    )
    return (
        _bounded_token(error.get("code"), _ERROR_TYPE),
        _bounded_token(error.get("param"), _ERROR_PARAM),
        _sanitize_message(error.get("message"), redact + generated),
    )


def _bounded_token(raw: object, pattern: re.Pattern[str]) -> str | None:
    if isinstance(raw, str) and pattern.fullmatch(raw) and not _looks_secret(raw):
        return raw
    return None


def _sanitize_message(raw: object, redact: tuple[str, ...]) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = _BEARER.sub(r"\1[redacted]", raw)
    text = _KEY.sub("[redacted]", text)
    for secret in redact:
        if isinstance(secret, str) and len(secret) >= 8 and secret in text:
            text = text.replace(secret, "[redacted]")
    text = " ".join(text.split())
    if len(text) > _MESSAGE_LIMIT:
        text = text[:_MESSAGE_LIMIT].rstrip()
    if _KEY.search(text) or re.search(r"(?i)\bbearer\s+[A-Za-z0-9]", text):
        return None
    if any(isinstance(secret, str) and len(secret) >= 8 and secret in text for secret in redact):
        return None
    return text or None


def _request_id(response: object) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    for name in _REQUEST_HEADERS:
        raw = headers.get(name)
        if isinstance(raw, str) and _REQUEST_ID.fullmatch(raw) and not _looks_secret(raw):
            return raw
    return None


def _looks_secret(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in _SECRET_PREFIXES)


class ProviderCallError(ProviderError):
    """A provider call did not return usable text.

    ``state`` is the technical state the stage stores. It is never a scope
    class.
    """

    def __init__(
        self,
        message: str,
        state: DecisionTechnicalState,
        *,
        retry_after_seconds: float | None = None,
        latency_seconds: float | None = None,
        diagnostic: ProviderDiagnostic | None = None,
    ) -> None:
        super().__init__(message)
        self.state = state
        self.retry_after_seconds = retry_after_seconds
        self.latency_seconds = latency_seconds
        self.diagnostic = diagnostic
        self.request_identity: dict[str, object] | None = None


def unavailable(
    message: str,
    *,
    latency_seconds: float | None = None,
    diagnostic: ProviderDiagnostic | None = None,
) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.provider_unavailable,
        latency_seconds=latency_seconds,
        diagnostic=diagnostic,
    )


def provider_failed(
    message: str,
    *,
    latency_seconds: float | None = None,
    diagnostic: ProviderDiagnostic | None = None,
) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.provider_error,
        latency_seconds=latency_seconds,
        diagnostic=diagnostic,
    )


def timed_out(
    message: str,
    *,
    latency_seconds: float | None = None,
    diagnostic: ProviderDiagnostic | None = None,
) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.timeout,
        latency_seconds=latency_seconds,
        diagnostic=diagnostic,
    )


def rate_limited(
    message: str,
    *,
    retry_after_seconds: float | None = None,
    latency_seconds: float | None = None,
    diagnostic: ProviderDiagnostic | None = None,
) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.rate_limited,
        retry_after_seconds=retry_after_seconds,
        latency_seconds=latency_seconds,
        diagnostic=diagnostic,
    )


class ProviderFatalError(ProviderCallError):
    """A failure that will reject every later document, such as bad credentials.

    The gateway does not retry it, and the stage stops the run after recording
    the document that hit it.
    """


def authentication_failed(
    message: str,
    *,
    latency_seconds: float | None = None,
    diagnostic: ProviderDiagnostic | None = None,
) -> ProviderFatalError:
    return ProviderFatalError(
        message,
        DecisionTechnicalState.provider_error,
        latency_seconds=latency_seconds,
        diagnostic=diagnostic,
    )


@dataclass(frozen=True)
class CompletionParams:
    """Decoding and transport settings that the cache key and the adapter share.

    ``timeout_seconds`` does not enter the cache key. It does not change the
    text a successful call returns.
    """

    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    diagnostic_model: type[BaseModel] | None = None


@dataclass(frozen=True)
class ProviderResponse:
    """Raw provider text plus token counts. Not a research record."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    latency_seconds: float | None = None
    requested_temperature: float | None = None
    effective_temperature: float | None = None
    cached_input_tokens: int | None = None
    finish_reason: str | None = None
    usage_reported: bool = True


class StructuredProvider(Protocol):
    """One method. The gateway owns cache, retry, repair, and validation."""

    provider_name: str

    def complete_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        params: CompletionParams,
    ) -> ProviderResponse:
        """Return raw text that should match ``schema``. Raise ProviderCallError."""
