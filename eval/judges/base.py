"""Uniform judge interface used by all eval scorers."""
from __future__ import annotations
import random, time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


_RETRY_KEYWORDS = (
    "rate limit", "ratelimit", "rate-limit", "429",
    "resource_exhausted", "resource exhausted", "resourceexhausted",
    "quota", "overloaded", "service unavailable", "503", "502", "504",
    "timeout", "timed out", "temporar",
    "connection", "apiconnection",
)


def call_with_retries(
    fn: Callable[[], Any],
    *,
    max_attempts: int = 5,
    base_delay: float = 2.0,
    jitter: float = 0.4,
) -> Any:
    """Invoke `fn()` and retry on transient/rate-limit errors with
    exponential backoff (2s, 4s, 8s, 16s, 32s) plus a small jitter."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            if any(kw in msg for kw in _RETRY_KEYWORDS):
                last_exc = e
                delay = base_delay * (2 ** attempt) * (1.0 + random.random() * jitter)
                time.sleep(delay)
                continue
            raise
    if last_exc is not None:
        raise last_exc


@dataclass
class JudgeResponse:
    """Result of a single judge call."""
    parsed: Optional[Dict[str, Any]]    # parsed JSON if successful, else None
    raw_text: str                       # the raw model output (for audit)
    latency_s: float
    tokens_in: int
    tokens_out: int
    error: Optional[str] = None         # None if call succeeded; error message otherwise
    extra: Dict[str, Any] = field(default_factory=dict)


class JudgeClient:
    """Base class — concrete subclasses wrap a particular provider/model."""
    name: str = "abstract"          # canonical identifier written to eval_results.jsonl
    provider: str = "abstract"      # "openai" / "gemini" / "xai"

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Dict[str, Any],
    ) -> JudgeResponse:
        """Run the prompt with structured JSON output. Sub-classes implement."""
        raise NotImplementedError
