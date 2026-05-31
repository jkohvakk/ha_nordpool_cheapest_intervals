"""Unit tests for Nordpool cheapest-interval selection (no Home Assistant required)."""

from datetime import date, datetime, timedelta

from cheapest_intervals import (
    build_cheapest_intervals,
    build_cheapest_interval_slots,
    cheap_hours_to_interval_count,
    cheapest_interval_slots,
    expand_slots_to_15min,
    format_interval_key,
    format_interval_plan,
    interval_start_key,
    is_interval_among_cheapest,
    parse_raw_slots,
    should_switch_on,
)


def _raw_quarter(hour: int, minute: int, value: float, day: date) -> dict:
    start = datetime(day.year, day.month, day.day, hour, minute, 0)
    end = start + timedelta(minutes=15)
    return {"start": start, "end": end, "value": value}


def _raw_hour(hour: int, value: float, day: date) -> dict:
    start = datetime(day.year, day.month, day.day, hour, 0, 0)
    end = start + timedelta(hours=1)
    return {"start": start, "end": end, "value": value}


def test_cheap_hours_to_interval_count():
    assert cheap_hours_to_interval_count(1.75) == 7
    assert cheap_hours_to_interval_count(3.25) == 13
    assert cheap_hours_to_interval_count(4) == 16
    assert cheap_hours_to_interval_count(0) == 0


def test_expand_hourly_slot_to_four_quarters():
    day = date(2026, 5, 24)
    slots = parse_raw_slots([_raw_hour(10, 0.42, day)])
    expanded = expand_slots_to_15min(slots)
    assert len(expanded) == 4
    assert [format_interval_key(interval_start_key(s.start)) for s in expanded] == [
        "10:00",
        "10:15",
        "10:30",
        "10:45",
    ]
    assert all(s.value == 0.42 for s in expanded)


def test_cheapest_seven_quarter_hour_intervals():
    day = date(2026, 5, 24)
    raw = [
        _raw_quarter(0, 0, 0.50, day),
        _raw_quarter(0, 15, 0.40, day),
        _raw_quarter(0, 30, 0.30, day),
        _raw_quarter(0, 45, 0.20, day),
        _raw_quarter(1, 0, 0.10, day),
        _raw_quarter(1, 15, 0.05, day),
        _raw_quarter(1, 30, 0.01, day),
        _raw_quarter(1, 45, 0.99, day),
    ]

    slots = parse_raw_slots(raw)
    cheapest = cheapest_interval_slots(slots, 7)
    labels = [format_interval_key(interval_start_key(s.start)) for s in cheapest]
    assert labels == ["00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30"]
    assert is_interval_among_cheapest(datetime(2026, 5, 24, 1, 30, 59), {interval_start_key(s.start) for s in cheapest})
    assert not is_interval_among_cheapest(datetime(2026, 5, 24, 1, 45, 0), {interval_start_key(s.start) for s in cheapest})


def test_hourly_nordpool_data_expands_before_picking_cheapest():
    day = date(2026, 5, 24)
    raw = [_raw_hour(h, 10.0 + h, day) for h in range(24)]
    raw[2]["value"] = 0.01
    raw[3]["value"] = 0.02

    slots = build_cheapest_interval_slots(raw, cheap_hours=2.0)
    labels = [format_interval_key(interval_start_key(s.start)) for s in slots]
    assert len(slots) == 8
    assert labels == [
        "02:00",
        "02:15",
        "02:30",
        "02:45",
        "03:00",
        "03:15",
        "03:30",
        "03:45",
    ]


def test_build_cheapest_intervals_from_raw_today():
    day = date(2026, 5, 24)
    raw_today = [
        _raw_quarter(2, 0, 0.01, day),
        _raw_quarter(2, 15, 0.02, day),
        _raw_quarter(10, 0, 0.99, day),
    ]

    result = build_cheapest_intervals(raw_today, cheap_hours=0.5)
    assert result == {
        interval_start_key(datetime(2026, 5, 24, 2, 0)),
        interval_start_key(datetime(2026, 5, 24, 2, 15)),
    }


def test_should_switch_on():
    assert should_switch_on(in_cheapest=False, boost_active=False) is False
    assert should_switch_on(in_cheapest=True, boost_active=False) is True
    assert should_switch_on(in_cheapest=False, boost_active=True) is True
    assert should_switch_on(in_cheapest=True, boost_active=True) is True


def test_format_interval_plan():
    day = date(2026, 5, 24)
    slots = parse_raw_slots([_raw_quarter(13, 45, 1.234, day)])
    plan = format_interval_plan(slots)
    assert "13:45" in plan
    assert "1.2340" in plan
