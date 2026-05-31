"""Pure Python helpers for picking cheapest electricity intervals from Nordpool data.

Works locally (pytest) and inside Home Assistant pyscript when imported from
``/config/pyscript/modules/cheapest_intervals.py``.

Nordpool sensor attributes (custom-components/nordpool):
  https://github.com/custom-components/nordpool

Config ``cheap_hours`` uses decimal *hours* where each 0.25 is one 15-minute
billing interval (e.g. ``1.75`` -> 7 intervals, ``3.25`` -> 13 intervals).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


def _row_field(row: Any, key: str) -> Any:
    """Read a Nordpool row field from a dict or attribute-style object."""
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _normalize_price_row(row: Any) -> dict[str, Any] | None:
    start = _row_field(row, "start")
    value = _row_field(row, "value")
    if start is None or value is None:
        return None
    return {
        "start": start,
        "end": _row_field(row, "end"),
        "value": value,
    }


def today_list_to_raw_rows(today: Sequence[Any], day: date) -> list[dict[str, Any]]:
    """Build ``raw_today``-shaped rows from Nordpool ``today`` (24 or 96 values)."""
    if not today:
        return []
    count = len(today)
    if count <= 0:
        return []
    minutes_per_slot = (24 * 60) // count
    base = datetime(day.year, day.month, day.day)
    rows: list[dict[str, Any]] = []
    for index, value in enumerate(today):
        if value is None or value == float("inf"):
            continue
        start = base + timedelta(minutes=index * minutes_per_slot)
        end = start + timedelta(minutes=minutes_per_slot)
        rows.append({"start": start, "end": end, "value": float(value)})
    return rows


def nordpool_price_rows(
    attrs: dict[str, Any] | None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Price rows for today from Nordpool sensor attributes.

    Prefer ``raw_today`` (timestamped). Fall back to ``today`` (value list) when
    ``raw_today`` is missing, empty, or does not parse into slots.
    """
    if not attrs:
        return []
    day = day or date.today()
    raw_today = attrs.get("raw_today")
    if isinstance(raw_today, (list, tuple)) and raw_today:
        rows = [row for item in raw_today if (row := _normalize_price_row(item))]
        if rows and parse_raw_slots(rows):
            return rows
    today = attrs.get("today")
    if isinstance(today, (list, tuple)) and today:
        return today_list_to_raw_rows(today, day)
    return []


def nordpool_diagnostics(attrs: dict[str, Any] | None) -> str:
    """Short summary of Nordpool attribute availability (for logs)."""
    if not attrs:
        return "attrs=empty"
    raw = attrs.get("raw_today")
    today = attrs.get("today")
    raw_count = len(raw) if isinstance(raw, (list, tuple)) else 0
    today_count = len(today) if isinstance(today, (list, tuple)) else 0
    return f"raw_today={raw_count} today={today_count} keys={sorted(attrs.keys())}"


def _slot_length_minutes(slot: PriceSlot) -> int:
    if slot.end is None:
        return 60
    delta = slot.end - slot.start
    minutes = int(delta.total_seconds() // 60)
    return max(1, minutes)


def parse_raw_slots(raw: Sequence[Any] | None) -> list[PriceSlot]:
    """Convert Nordpool price rows to ``PriceSlot`` list."""
    if not raw:
        return []
    slots: list[PriceSlot] = []
    for row in raw:
        normalized = _normalize_price_row(row)
        if normalized is None:
            continue
        start = normalized["start"]
        value = normalized["value"]
        end = normalized.get("end")
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


def should_switch_on(in_cheapest: bool, boost_active: bool) -> bool:
    """True when boost override is on or the current interval is in today's plan."""
    return boost_active or in_cheapest


def is_in_hour_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    """True when ``now`` is in ``[start_hour:00, end_hour:00)``, including overnight wrap."""
    minute_of_day = now.hour * 60 + now.minute
    start = start_hour * 60
    end = end_hour * 60
    if start < end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


def should_switch_on_car(
    in_cheapest: bool,
    in_night_window: bool,
    boost_active: bool = False,
) -> bool:
    """True when boost, cheapest slot, or night window applies."""
    return boost_active or in_cheapest or in_night_window


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
