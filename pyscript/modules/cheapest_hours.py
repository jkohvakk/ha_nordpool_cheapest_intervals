"""Pure Python helpers for picking cheapest electricity intervals from Nordpool data.

Works locally (pytest) and inside Home Assistant pyscript when imported from
``/config/pyscript/modules/cheapest_hours.py``.

Nordpool sensor attributes (custom-components/nordpool):
  https://github.com/custom-components/nordpool

Configuration uses decimal *hours* where each 0.25 represents one 15-minute
billing interval (e.g. ``1.75`` -> 7 intervals, ``3.25`` -> 13 intervals).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence

INTERVALS_PER_HOUR = 4
QUARTER_MINUTES = 15
IntervalKey = tuple[int, int, int, int, int]


def cheap_hours_to_interval_count(cheap_hours: float) -> int:
    """Convert configured decimal hours to a count of 15-minute intervals."""
    if cheap_hours <= 0:
        return 0
    return round(cheap_hours * INTERVALS_PER_HOUR)


def interval_start_key(value: datetime) -> IntervalKey:
    """Normalize a timestamp to the start of its 15-minute interval."""
    parts = value.timetuple()
    quarter_minute = (parts[4] // QUARTER_MINUTES) * QUARTER_MINUTES
    return (parts[0], parts[1], parts[2], parts[3], quarter_minute)


def format_interval_key(key: IntervalKey) -> str:
    """Human-readable ``HH:MM`` label for logs."""
    return f"{key[3]:02d}:{key[4]:02d}"


@dataclass(frozen=True)
class PriceSlot:
    """One priced interval from Nordpool ``raw_today``."""

    start: datetime
    value: float
    end: datetime | None = None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _slot_length_minutes(slot: PriceSlot) -> int:
    if slot.end is None:
        return 60
    delta = slot.end - slot.start
    minutes = int(delta.total_seconds() // 60)
    return max(1, minutes)


def parse_raw_slots(raw: Sequence[dict[str, Any]] | None) -> list[PriceSlot]:
    """Convert Nordpool ``raw_today`` entries to ``PriceSlot`` list."""
    if not raw:
        return []
    slots: list[PriceSlot] = []
    for row in raw:
        start = row.get("start")
        value = row.get("value")
        if start is None or value is None:
            continue
        end = row.get("end")
        slots.append(
            PriceSlot(
                start=_parse_timestamp(start),
                end=_parse_timestamp(end) if end is not None else None,
                value=float(value),
            )
        )
    return slots


def expand_slots_to_15min(slots: Iterable[PriceSlot]) -> list[PriceSlot]:
    """Expand hourly (or longer) Nordpool rows into 15-minute slots with the same price."""
    expanded: list[PriceSlot] = []
    for slot in slots:
        length = _slot_length_minutes(slot)
        if length <= QUARTER_MINUTES:
            expanded.append(slot)
            continue
        steps = length // QUARTER_MINUTES
        for step in range(steps):
            expanded.append(
                PriceSlot(
                    start=slot.start + timedelta(minutes=QUARTER_MINUTES * step),
                    value=slot.value,
                )
            )
    return expanded


def today_quarter_slots(raw_today: Sequence[dict[str, Any]] | None) -> list[PriceSlot]:
    """All of today's 15-minute slots from ``raw_today``."""
    return expand_slots_to_15min(parse_raw_slots(raw_today))


def cheapest_interval_slots(slots: Sequence[PriceSlot], n: int) -> list[PriceSlot]:
    """Return the ``n`` cheapest 15-minute ``PriceSlot`` rows, sorted by start time.

    Uses builtin ``sorted`` with pre-built tuple keys instead of ``key=lambda``;
    pyscript wraps lambdas as async functions, which makes ``sorted(..., key=...)``
    compare coroutines and fail. Tuple comparison needs no key function.
    """
    if n <= 0 or not slots:
        return []
    by_value = sorted([(s.value, i, s) for i, s in enumerate(slots)])
    chosen = [item[2] for item in by_value[:n]]
    by_start = sorted(
        [(interval_start_key(s.start), i, s) for i, s in enumerate(chosen)]
    )
    return [item[2] for item in by_start]


def cheapest_interval_keys(
    slots: Sequence[PriceSlot],
    n: int,
) -> set[IntervalKey]:
    """Return start keys for the ``n`` cheapest 15-minute intervals."""
    return {interval_start_key(s.start) for s in cheapest_interval_slots(slots, n)}


def is_interval_among_cheapest(now: datetime, cheapest: set[IntervalKey]) -> bool:
    return interval_start_key(now) in cheapest


def format_interval_plan(slots: Sequence[PriceSlot]) -> str:
    """Multi-line plan: each 15-minute interval with price."""
    if not slots:
        return "(no intervals)"
    lines = [
        f"  {format_interval_key(interval_start_key(s.start))}  {s.value:.4f}"
        for s in slots
    ]
    return "\n".join(lines)


def build_cheapest_intervals(
    raw_today: Sequence[dict[str, Any]] | None,
    cheap_hours: float,
) -> set[IntervalKey]:
    """Cheapest interval start keys for today from ``raw_today``."""
    n = cheap_hours_to_interval_count(cheap_hours)
    return cheapest_interval_keys(today_quarter_slots(raw_today), n)


def build_cheapest_interval_slots(
    raw_today: Sequence[dict[str, Any]] | None,
    cheap_hours: float,
) -> list[PriceSlot]:
    """Cheapest 15-minute slots for today from ``raw_today`` (for logging)."""
    n = cheap_hours_to_interval_count(cheap_hours)
    return cheapest_interval_slots(today_quarter_slots(raw_today), n)
