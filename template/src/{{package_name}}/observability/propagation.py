"""Trace context for messages (Redis Streams): producer injects, consumer extracts.

Usage is described in the `add-event-handler` skill (.claude/skills).
"""

from collections.abc import Mapping

from opentelemetry import propagate
from opentelemetry.context import Context


def inject_trace_context(headers: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return `headers` plus W3C `traceparent`/`tracestate` of the current span."""
    carrier = dict(headers or {})
    propagate.inject(carrier)
    return carrier


def extract_trace_context(headers: Mapping[str, str]) -> Context:
    """Build a context whose parent is the span that produced the message."""
    return propagate.extract(dict(headers))
