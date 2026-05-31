"""Pure helpers for weather-driven floor heating.

Works locally (pytest) and inside Home Assistant pyscript when imported from
``/config/pyscript/modules/weather_forecast.py``.

Heating duration is derived from today's average forecast temperature:

  * ``avg <= -20 C``  -> 24 h (always on)
  * ``-20 C .. 0 C``  -> linear 24 h -> 12 h
  * ``0 C .. +20 C``  -> linear 12 h -> 0 h
  * ``avg >= +20 C``  -> 0 h (always off)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

COLD_LIMIT_C = -20.0
WARM_LIMIT_C = 20.0
HOURS_AT_ZERO = 12.0
MAX_HOURS = 24.0


def floor_heating_hours_from_temp(avg_c: float) -> float:
    """Heated hours per day for an average forecast temperature in Celsius."""
    if avg_c <= COLD_LIMIT_C:
        return MAX_HOURS
    if avg_c >= WARM_LIMIT_C:
        return 0.0
    if avg_c <= 0:
        # 12 h at 0 C rising to 24 h at -20 C
        return HOURS_AT_ZERO + (-avg_c / -COLD_LIMIT_C) * (MAX_HOURS - HOURS_AT_ZERO)
    # 12 h at 0 C falling to 0 h at +20 C
    return HOURS_AT_ZERO * (1 - avg_c / WARM_LIMIT_C)


def _entry_datetime(entry: Any) -> datetime | None:
    raw = entry.get("datetime") if isinstance(entry, dict) else getattr(entry, "datetime", None)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _entry_temperature(entry: Any) -> float | None:
    value = entry.get("temperature") if isinstance(entry, dict) else getattr(entry, "temperature", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def daily_average_from_hourly_forecast(
    forecast: Sequence[Any] | None,
    day: date | None = None,
) -> float | None:
    """Average of ``temperature`` for forecast entries whose date matches ``day``.

    Returns ``None`` when no matching entries with a temperature are found.
    """
    if not forecast:
        return None
    day = day or date.today()
    temps: list[float] = []
    for entry in forecast:
        when = _entry_datetime(entry)
        if when is None or when.date() != day:
            continue
        temp = _entry_temperature(entry)
        if temp is not None:
            temps.append(temp)
    if not temps:
        return None
    return sum(temps) / len(temps)
