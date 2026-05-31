"""Unit tests for weather-driven floor heating (no Home Assistant required)."""

from datetime import date, datetime, timedelta

from weather_forecast import (
    daily_average_from_hourly_forecast,
    floor_heating_hours_from_temp,
)


def test_hours_extreme_cold_always_on():
    assert floor_heating_hours_from_temp(-20) == 24.0
    assert floor_heating_hours_from_temp(-30) == 24.0


def test_hours_extreme_warm_always_off():
    assert floor_heating_hours_from_temp(20) == 0.0
    assert floor_heating_hours_from_temp(25) == 0.0


def test_hours_zero_degrees_is_twelve():
    assert floor_heating_hours_from_temp(0) == 12.0


def test_hours_linear_below_zero():
    # halfway between 0 and -20 -> halfway between 12 and 24
    assert floor_heating_hours_from_temp(-10) == 18.0


def test_hours_linear_above_zero():
    # halfway between 0 and +20 -> halfway between 12 and 0
    assert floor_heating_hours_from_temp(10) == 6.0


def test_daily_average_filters_to_day():
    day = date(2026, 1, 15)
    base = datetime(2026, 1, 15, 0, 0)
    forecast = [
        {"datetime": (base + timedelta(hours=h)).isoformat(), "temperature": float(h)}
        for h in range(24)
    ]
    # add tomorrow entries that must be ignored
    forecast += [
        {"datetime": datetime(2026, 1, 16, 12, 0).isoformat(), "temperature": 99.0}
    ]
    avg = daily_average_from_hourly_forecast(forecast, day)
    assert avg == sum(range(24)) / 24


def test_daily_average_none_when_no_match():
    forecast = [{"datetime": "2026-01-16T12:00:00", "temperature": 5.0}]
    assert daily_average_from_hourly_forecast(forecast, date(2026, 1, 15)) is None


def test_daily_average_empty():
    assert daily_average_from_hourly_forecast([], date(2026, 1, 15)) is None
    assert daily_average_from_hourly_forecast(None, date(2026, 1, 15)) is None
