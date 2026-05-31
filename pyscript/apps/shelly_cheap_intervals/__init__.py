"""Pyscript app: turn Shelly switches on during the cheapest Nordpool 15-min intervals.

Configure in ``configuration.yaml`` under ``pyscript.apps.shelly_cheap_intervals``.
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
    is_interval_among_cheapest,
    should_switch_on,
)

_DEFAULT_BOOST_TIMER = "timer.water_heating_boost"
_DEFAULT_BOOST_DURATION = "06:00:00"


def _cfg():
    return pyscript.app_config


def _nordpool_attrs():
    return state.getattr(_cfg()["nordpool_sensor"]) or {}


def _cheap_hours() -> float:
    return float(_cfg().get("cheap_hours", 3))


def _boost_timer_entity() -> str | None:
    return _cfg().get("boost_timer")


def _boost_duration() -> str:
    return _cfg().get("boost_duration", _DEFAULT_BOOST_DURATION)


def _boost_active() -> bool:
    timer_entity = _boost_timer_entity()
    if not timer_entity:
        return False
    return state.get(timer_entity) == "active"


def _raw_today():
    return _nordpool_attrs().get("raw_today")


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
    boost_active = _boost_active()
    on = should_switch_on(in_cheapest, boost_active)
    log.warning(
        f"shelly_cheap_intervals: now={format_interval_key(interval_start_key(now))} "
        f"in_cheapest={in_cheapest} boost_active={boost_active} switch_on={on} "
        f"(plan has {len(cheapest)} intervals)"
    )
    _apply_switch(on)


@time_trigger("startup")
def shelly_cheap_intervals_startup():
    cheap_hours = _cheap_hours()
    intervals = cheap_hours_to_interval_count(cheap_hours)
    log.warning(
        f"shelly_cheap_intervals: app loaded, cheap_hours={cheap_hours} "
        f"({intervals} x 15 min), config={_cfg()}"
    )


@time_trigger("cron(0,15,30,45 * * * *)")
def shelly_cheap_intervals_tick():
    """At each 15-minute boundary, set switch according to plan or boost."""
    _evaluate_and_apply_switch()


@time_trigger("cron(0 14 * * *)")
def shelly_cheap_intervals_daily_plan_log():
    """Log today's plan after Nordpool refresh (~14:00 Finnish time)."""
    slots = _cheapest_interval_slots_today()
    log.warning(
        f"shelly_cheap_intervals: {len(slots)} cheapest 15-min intervals today:\n"
        f"{format_interval_plan(slots)}"
    )


# Entity id must match ``boost_timer`` in app config (default: timer.water_heating_boost).
@state_trigger(f"{_DEFAULT_BOOST_TIMER} == 'idle'")
def shelly_cheap_intervals_boost_ended(old_value=None):
    """Re-evaluate switch when timed boost finishes."""
    if old_value != "active":
        return
    log.warning("shelly_cheap_intervals: boost ended, re-evaluating switch")
    _evaluate_and_apply_switch()


@service
def shelly_cheap_intervals_apply_now():
    """Force evaluation now (Developer Tools -> pyscript.shelly_cheap_intervals_apply_now)."""
    _evaluate_and_apply_switch()


@service
def shelly_cheap_intervals_show_cheapest():
    """Log today's cheapest 15-minute intervals with prices (Developer Tools)."""
    slots = _cheapest_interval_slots_today()
    log.warning(
        f"shelly_cheap_intervals: {len(slots)} cheapest 15-min intervals today "
        f"(cheap_hours={_cheap_hours()}):\n{format_interval_plan(slots)}"
    )


@service
def shelly_cheap_intervals_boost_start(duration=None):
    """Start timed heating boost (switch on until timer expires)."""
    timer_entity = _boost_timer_entity()
    if not timer_entity:
        log.error("shelly_cheap_intervals: boost_timer not configured")
        return
    duration = duration or _boost_duration()
    switch.turn_on(entity_id=_cfg()["shelly_switch"])
    timer.start(entity_id=timer_entity, duration=duration)
    log.warning(f"shelly_cheap_intervals: boost started for {duration}")


@service
def shelly_cheap_intervals_boost_stop():
    """Cancel heating boost and re-evaluate switch from Nordpool plan."""
    timer_entity = _boost_timer_entity()
    if not timer_entity:
        log.error("shelly_cheap_intervals: boost_timer not configured")
        return
    timer.cancel(entity_id=timer_entity)
    log.warning("shelly_cheap_intervals: boost cancelled")
    _evaluate_and_apply_switch()
