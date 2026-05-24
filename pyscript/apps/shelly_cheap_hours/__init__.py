"""Pyscript app: turn Shelly switches on during the cheapest Nordpool 15-min intervals.

Configure in ``/config/pyscript/config.yaml`` (see README). Reload is automatic
when this file changes.
"""

from datetime import datetime

from cheapest_hours import (
    build_cheapest_interval_slots,
    build_cheapest_intervals,
    cheap_hours_to_interval_count,
    format_interval_key,
    format_interval_plan,
    interval_start_key,
    is_interval_among_cheapest,
)


def _cfg():
    return pyscript.app_config


def _nordpool_attrs():
    return state.getattr(_cfg()["nordpool_sensor"]) or {}


def _cheap_hours() -> float:
    return float(_cfg().get("cheap_hours", 3))


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


@time_trigger("startup")
def shelly_cheap_hours_startup():
    cheap_hours = _cheap_hours()
    intervals = cheap_hours_to_interval_count(cheap_hours)
    log.warning(
        f"shelly_cheap_hours: app loaded, cheap_hours={cheap_hours} "
        f"({intervals} x 15 min), config={_cfg()}"
    )


@time_trigger("cron(0,15,30,45 * * * *)")
def shelly_cheap_hours_interval():
    """At each 15-minute boundary, set switch according to cheapest-interval plan."""
    now = datetime.now()
    cheapest = _cheapest_interval_keys_today()
    on = is_interval_among_cheapest(now, cheapest)
    log.warning(
        f"shelly_cheap_hours: now={format_interval_key(interval_start_key(now))} "
        f"in_cheapest={on} (plan has {len(cheapest)} intervals)"
    )
    _apply_switch(on)


@time_trigger("cron(0 14 * * *)")
def shelly_cheap_hours_daily_plan_log():
    """Log today's plan after Nordpool refresh (~14:00 Finnish time)."""
    slots = _cheapest_interval_slots_today()
    log.warning(
        f"shelly_cheap_hours: {len(slots)} cheapest 15-min intervals today:\n"
        f"{format_interval_plan(slots)}"
    )


@service
def shelly_cheap_hours_apply_now():
    """Force evaluation now (Developer Tools -> pyscript.shelly_cheap_hours_apply_now)."""
    shelly_cheap_hours_interval()


@service
def shelly_cheap_hours_show_cheapest_intervals():
    """Log today's cheapest 15-minute intervals with prices (Developer Tools)."""
    slots = _cheapest_interval_slots_today()
    log.warning(
        f"shelly_cheap_hours: {len(slots)} cheapest 15-min intervals today "
        f"(cheap_hours={_cheap_hours()}):\n{format_interval_plan(slots)}"
    )
