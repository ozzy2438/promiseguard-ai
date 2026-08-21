"""Stable error taxonomy for external operational adapters.

These errors are raised by OMS, WMS and carrier adapters. The governed action
gateway maps them onto durable action status without exposing vendor payloads
to decision logic.
"""

from __future__ import annotations

from enum import StrEnum


class AdapterErrorClass(StrEnum):
    SUCCESS = "SUCCESS"
    RETRYABLE = "RETRYABLE"
    FATAL = "FATAL"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    MALFORMED = "MALFORMED"
    AUTH = "AUTH"


class AdapterError(RuntimeError):
    """Base class for adapter failures with a stable error class."""

    error_class: AdapterErrorClass = AdapterErrorClass.FATAL
    retryable: bool = False
    ambiguous: bool = False


class ActionExecutionError(AdapterError):
    """Raised when a governed action cannot be completed safely."""

    error_class = AdapterErrorClass.FATAL
    retryable = False
    ambiguous = False


class AdapterTimeout(AdapterError, TimeoutError):
    """Adapter exceeded its configured request timeout."""

    error_class = AdapterErrorClass.RETRYABLE
    retryable = True
    ambiguous = False


class AmbiguousProviderTimeout(AdapterTimeout):
    """Provider timed out after the external state may already have changed."""

    error_class = AdapterErrorClass.AMBIGUOUS
    retryable = False
    ambiguous = True


class AdapterRateLimited(AdapterError):
    """Provider refused the call because a rate limit was exceeded."""

    error_class = AdapterErrorClass.RATE_LIMITED
    retryable = True
    ambiguous = False


class MalformedAdapterResponse(AdapterError):
    """Provider returned a payload that failed the adapter contract schema."""

    error_class = AdapterErrorClass.MALFORMED
    retryable = False
    ambiguous = True


class AdapterAuthError(AdapterError):
    """Authentication or authorisation to the external system failed."""

    error_class = AdapterErrorClass.AUTH
    retryable = False
    ambiguous = False
