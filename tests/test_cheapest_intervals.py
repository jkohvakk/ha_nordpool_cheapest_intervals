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
    is_in_hour_window,
    is_interval_among_cheapest,
    nordpool_price_rows,
    parse_raw_slots,
    should_switch_on,
    should_switch_on_car,
    today_list_to_raw_rows,
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


def test_is_in_hour_window_overnight():
    assert not is_in_hour_window(datetime(2026, 5, 24, 21, 45), 22, 7)
    assert is_in_hour_window(datetime(2026, 5, 24, 22, 0), 22, 7)
    assert is_in_hour_window(datetime(2026, 5, 24, 23, 30), 22, 7)
    assert is_in_hour_window(datetime(2026, 5, 25, 0, 0), 22, 7)
    assert is_in_hour_window(datetime(2026, 5, 25, 6, 45), 22, 7)
    assert not is_in_hour_window(datetime(2026, 5, 25, 7, 0), 22, 7)
    assert not is_in_hour_window(datetime(2026, 5, 25, 12, 0), 22, 7)


def test_is_in_hour_window_same_day():
    assert is_in_hour_window(datetime(2026, 5, 24, 9, 0), 8, 17)
    assert not is_in_hour_window(datetime(2026, 5, 24, 7, 59), 8, 17)
    assert not is_in_hour_window(datetime(2026, 5, 24, 17, 0), 8, 17)


def test_should_switch_on_car():
    assert should_switch_on_car(False, False, False) is False
    assert should_switch_on_car(True, False, False) is True
    assert should_switch_on_car(False, True, False) is True
    assert should_switch_on_car(False, False, True) is True


def test_nordpool_price_rows_prefers_raw_today():
    day = date(2026, 5, 24)
    attrs = {
        "raw_today": [_raw_quarter(2, 0, 0.01, day)],
        "today": [9.99],
    }
    rows = nordpool_price_rows(attrs, day)
    assert len(rows) == 1
    assert rows[0]["value"] == 0.01


def test_nordpool_price_rows_falls_back_to_today_list():
    day = date(2026, 5, 24)
    attrs = {"today": [0.50, 0.40, 0.30, 0.20] + [1.0] * 20}
    rows = nordpool_price_rows(attrs, day)
    assert len(rows) == 24
    assert rows[1]["value"] == 0.40


def test_nordpool_price_rows_falls_back_when_raw_today_unparseable():
    day = date(2026, 5, 24)
    attrs = {
        "raw_today": [{"start": "bad", "value": None}],
        "today": [0.50, 0.40] + [1.0] * 22,
    }
    rows = nordpool_price_rows(attrs, day)
    assert len(rows) == 24


def test_build_cheapest_intervals_from_today_list_fallback():
    day = date(2026, 5, 24)
    today = [float(h) for h in range(24)]
    rows = today_list_to_raw_rows(today, day)
    cheapest = build_cheapest_intervals(rows, cheap_hours=7)
    assert len(cheapest) == 28


def test_format_interval_plan():
    day = date(2026, 5, 24)
    slots = parse_raw_slots([_raw_quarter(13, 45, 1.234, day)])
    plan = format_interval_plan(slots)
    assert "13:45" in plan
    assert "1.2340" in plan
