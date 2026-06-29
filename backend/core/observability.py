"""
Datadog APM + metrics integration.

ddtrace is an optional dependency — if not installed the module degrades to no-ops
so the rest of the codebase doesn't need try/except guards.
"""
from __future__ import annotations

import contextlib
import logging
from typing import Generator

logger = logging.getLogger("revCreate.observability")

# ── ddtrace ──────────────────────────────────────────────────────────────────

try:
    from ddtrace import tracer as _tracer

    def trace(name: str, resource: str, **tags):
        @contextlib.contextmanager
        def _ctx() -> Generator:
            with _tracer.trace(name, resource=resource) as span:
                for k, v in tags.items():
                    span.set_tag(k, v)
                yield span
        return _ctx()

except ImportError:
    @contextlib.contextmanager
    def trace(name: str, resource: str, **tags):  # type: ignore[misc]
        yield None

# ── DogStatsD metrics ─────────────────────────────────────────────────────────

try:
    from datadog import statsd as _statsd

    def histogram(metric: str, value: float, tags: list[str] | None = None) -> None:
        _statsd.histogram(metric, value, tags=tags or [])

    def increment(metric: str, tags: list[str] | None = None) -> None:
        _statsd.increment(metric, tags=tags or [])

except ImportError:
    def histogram(metric: str, value: float, tags: list[str] | None = None) -> None:  # type: ignore[misc]
        pass

    def increment(metric: str, tags: list[str] | None = None) -> None:  # type: ignore[misc]
        pass
