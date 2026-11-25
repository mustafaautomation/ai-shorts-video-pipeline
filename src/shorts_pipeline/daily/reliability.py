"""Retries, poll timeouts, and a per-run cost cap.

Free providers charge zero. Paid adapters record an estimate and stop the run
before the cap, so a poll loop cannot spend without a bound.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


class PollTimeout(TimeoutError):
    """A wait-and-poll loop passed its hard cap."""


class CostCapExceeded(RuntimeError):
    """The next paid call would pass the per-run cap."""


def with_backoff(
    operation: Callable[[], object],
    *,
    attempts: int = 3,
    base_seconds: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
    retry_on: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError, OSError),
) -> object:
    """Retry transient failures. Wait doubles after each miss."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last: BaseException | None = None
    for index in range(attempts):
        try:
            return operation()
        except retry_on as exc:
            last = exc
            if index == attempts - 1:
                raise
            sleep(base_seconds * (2**index))
    raise last or RuntimeError("retry failed")


def poll_until(
    fetch: Callable[[], object],
    *,
    is_done: Callable[[object], bool],
    interval: float,
    timeout: float,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> object:
    """Call fetch until is_done, or raise PollTimeout. The clock is injectable."""
    if interval <= 0 or timeout <= 0:
        raise ValueError("interval and timeout must be positive")
    started = now()
    while True:
        value = fetch()
        if is_done(value):
            return value
        elapsed = now() - started
        if elapsed >= timeout:
            raise PollTimeout(f"poll exceeded {timeout:.0f}s (last={value!r})")
        sleep(min(interval, timeout - elapsed))


# Estimated USD for one call. Free defaults stay at zero.
PRICE_USD = {
    "fixture": 0.0,
    "gradient": 0.0,
    "ken_burns": 0.0,
    "edge": 0.0,
    "offline_voice": 0.0,
    "groq": 0.0,
    "gemini": 0.0,
    "ffmpeg": 0.0,
    "browser": 0.0,
    "flux": 0.03,
    "kling": 0.10,
    "veo": 0.20,
    "elevenlabs": 0.03,
    "openai_whisper": 0.006,
    "creatomate": 0.08,
    "apify": 0.01,
}


@dataclass
class CostLedger:
    cap_usd: float = 1.0
    charges: list[tuple[str, float]] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(amount for _, amount in self.charges), 6)

    def charge(self, provider: str, *, units: int = 1) -> float:
        price = PRICE_USD.get(provider)
        if price is None:
            raise KeyError(f"unknown provider price: {provider}")
        amount = round(price * units, 6)
        if self.total + amount > self.cap_usd + 1e-9:
            raise CostCapExceeded(
                f"{provider} would bring the run to ${self.total + amount:.2f}, "
                f"over the ${self.cap_usd:.2f} cap"
            )
        self.charges.append((provider, amount))
        return amount
