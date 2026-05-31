"""Pyscript app: car charging on cheapest hours and/or a nightly window.

Configure in ``configuration.yaml`` under ``pyscript.apps.shelly_car_charging``.
Reload is automatic when this file changes.
"""

from datetime import datetime

from cheapest_intervals import (
    build_cheapest_interval_slots,
    build_cheapest_intervals,
    cheap_hours_to_interval_count,
    format_interval_key,
    format_interval_plan,
    interval_start_key,
    is_in_hour_window,
    is_interval_among_cheapest,
    nordpool_diagnostics,
    nordpool_price_rows,
    should_switch_on_car,
)

_DEFAULT_BOOST_TIMER = "timer.car_charging_boost"
_DEFAULT_BOOST_DURATION = "06:00:00"
_DEFAULT_NIGHT_START = 22
_DEFAULT_NIGHT_END = 7


def _cfg():
    return pyscript.app_config


def _nordpool_sensor_entity() -> str:
    entity = _cfg().get("nordpool_sensor")
    if not entity:
        return ""
    return str(entity).strip()


def _nordpool_attrs():
    entity = _nordpool_sensor_entity()
    if not entity:
        return {}
    return state.getattr(entity) or {}


def _price_rows():
    return nordpool_price_rows(_nordpool_attrs(), datetime.now().date())


def _cheap_hours() -> float:
    return float(_cfg().get("cheap_hours", 7))


def _night_start() -> int:
    return int(_cfg().get("night_start", _DEFAULT_NIGHT_START))


def _night_end() -> int:
    return int(_cfg().get("night_end", _DEFAULT_NIGHT_END))


def _boost_timer_entity() -> str | None:
    return _cfg().get("boost_timer")


def _boost_duration() -> str:
    return _cfg().get("boost_duration", _DEFAULT_BOOST_DURATION)


def _boost_active() -> bool:
    timer_entity = _boost_timer_entity()
    if not timer_entity:
        return False
    if not state.exist(timer_entity):
        return False
    return state.get(timer_entity) == "active"


def _raw_today():
    return _price_rows()


def _cheapest_interval_keys_today():
    return build_cheapest_intervals(_raw_today(), _cheap_hours())


def _cheapest_interval_slots_today():
    return build_cheapest_interval_slots(_raw_today(), _cheap_hours())


def _apply_switch(should_on: bool) -> None:
    entity = _cfg()["shelly_switch"]
    if should_on:
        switch.turn_on(entity_id=entity)
    else:
        switch.turn_off(entity_id=entity)


def _evaluate_and_apply_switch() -> None:
    now = datetime.now()
    cheapest = _cheapest_interval_keys_today()
    in_cheapest = is_interval_among_cheapest(now, cheapest)
    in_night = is_in_hour_window(now, _night_start(), _night_end())
    boost_active = _boost_active()
    on = should_switch_on_car(in_cheapest, in_night, boost_active)
    if len(cheapest) == 0 and _cheap_hours() > 0:
        attrs = _nordpool_attrs()
        log.warning(
            f"shelly_car_charging: no price rows parsed "
            f"(sensor={_nordpool_sensor_entity()!r}, "
            f"{nordpool_diagnostics(attrs)}, "
            f"price_rows={len(_price_rows())})"
        )
    log.warning(
        f"shelly_car_charging: now={format_interval_key(interval_start_key(now))} "
        f"in_cheapest={in_cheapest} in_night={in_night} boost_active={boost_active} "
        f"switch_on={on} (plan has {len(cheapest)} cheapest intervals, "
        f"night={_night_start():02d}:00-{_night_end():02d}:00)"
    )
    _apply_switch(on)


@time_trigger("startup")
def shelly_car_charging_startup():
    cheap_hours = _cheap_hours()
    intervals = cheap_hours_to_interval_count(cheap_hours)
    log.warning(
        f"shelly_car_charging: app loaded, cheap_hours={cheap_hours} "
        f"({intervals} x 15 min), night={_night_start():02d}:00-{_night_end():02d}:00, "
        f"config={_cfg()}"
    )


@time_trigger("cron(0,15,30,45 * * * *)")
def shelly_car_charging_tick():
    """At each 15-minute boundary, set switch according to plan or boost."""
    _evaluate_and_apply_switch()


@time_trigger("cron(0 14 * * *)")
def shelly_car_charging_daily_plan_log():
    """Log today's plan after Nordpool refresh (~14:00 Finnish time)."""
    slots = _cheapest_interval_slots_today()
    log.warning(
        f"shelly_car_charging: {len(slots)} cheapest 15-min intervals today "
        f"(cheap_hours={_cheap_hours()}), night={_night_start():02d}:00-{_night_end():02d}:00:\n"
        f"{format_interval_plan(slots)}"
    )


# Entity id must match ``boost_timer`` in app config (default: timer.car_charging_boost).
@state_trigger(f"{_DEFAULT_BOOST_TIMER} == 'idle'")
def shelly_car_charging_boost_ended(old_value=None):
    """Re-evaluate switch when timed boost finishes."""
    if old_value != "active":
        return
    log.warning("shelly_car_charging: boost ended, re-evaluating switch")
    _evaluate_and_apply_switch()


@service
def shelly_car_charging_apply_now():
    """Force evaluation now (Developer Tools -> pyscript.shelly_car_charging_apply_now)."""
    _evaluate_and_apply_switch()


@service
def shelly_car_charging_show_plan():
    """Log today's cheapest intervals and night window (Developer Tools)."""
    attrs = _nordpool_attrs()
    rows = _price_rows()
    slots = _cheapest_interval_slots_today()
    log.warning(
        f"shelly_car_charging: {len(slots)} cheapest 15-min intervals today "
        f"(cheap_hours={_cheap_hours()}), night={_night_start():02d}:00-{_night_end():02d}:00, "
        f"sensor={_nordpool_sensor_entity()!r}, price_rows={len(rows)}, "
        f"{nordpool_diagnostics(attrs)}:\n{format_interval_plan(slots)}"
    )
    if not _nordpool_sensor_entity():
        log.error(
            "shelly_car_charging: nordpool_sensor missing in app config — "
            "set the same entity as shelly_cheap_intervals"
        )


@service
def shelly_car_charging_boost_start(duration=None):
    """Start timed charging boost (switch on until timer expires)."""
    timer_entity = _boost_timer_entity()
    if not timer_entity:
        log.error("shelly_car_charging: boost_timer not configured")
        return
    duration = duration or _boost_duration()
    switch.turn_on(entity_id=_cfg()["shelly_switch"])
    timer.start(entity_id=timer_entity, duration=duration)
    log.warning(f"shelly_car_charging: boost started for {duration}")


@service
def shelly_car_charging_boost_stop():
    """Cancel charging boost and re-evaluate switch from plan."""
    timer_entity = _boost_timer_entity()
    if not timer_entity:
        log.error("shelly_car_charging: boost_timer not configured")
        return
    timer.cancel(entity_id=timer_entity)
    log.warning("shelly_car_charging: boost cancelled")
    _evaluate_and_apply_switch()
