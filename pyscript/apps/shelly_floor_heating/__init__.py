"""Pyscript app: floor heating, with heated hours derived from weather forecast.

Configure in ``configuration.yaml`` under ``pyscript.apps.shelly_floor_heating``.
Reload is automatic when this file changes.

Heated hours scale with today's average forecast temperature (see
``weather_forecast.floor_heating_hours_from_temp``):
  * <= -20 C  -> always on
  * 0 C       -> 12 heated hours (cheapest intervals)
  * >= +20 C  -> always off
"""

from datetime import datetime

from cheapest_intervals import (
    build_cheapest_intervals,
    build_cheapest_interval_slots,
    cheap_hours_to_interval_count,
    format_interval_key,
    format_interval_plan,
    interval_start_key,
    is_interval_among_cheapest,
    nordpool_diagnostics,
    nordpool_price_rows,
)
from weather_forecast import (
    MAX_HOURS,
    floor_heating_hours_from_temp,
)


def _cfg():
    return pyscript.app_config


def _nordpool_sensor_entity() -> str:
    entity = _cfg().get("nordpool_sensor")
    return str(entity).strip() if entity else ""


def _nordpool_attrs():
    entity = _nordpool_sensor_entity()
    if not entity:
        return {}
    return state.getattr(entity) or {}


def _price_rows():
    return nordpool_price_rows(_nordpool_attrs(), datetime.now().date())


def _forecast_sensor_entity() -> str:
    entity = _cfg().get("forecast_sensor")
    return str(entity).strip() if entity else ""


def _avg_forecast_temp() -> float | None:
    entity = _forecast_sensor_entity()
    if not entity or not state.exist(entity):
        return None
    value = state.get(entity)
    if value in (None, "unknown", "unavailable", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _heated_hours() -> float | None:
    avg = _avg_forecast_temp()
    if avg is None:
        return None
    return floor_heating_hours_from_temp(avg)


def _apply_switch(should_on: bool) -> None:
    entity = _cfg()["shelly_switch"]
    if should_on:
        switch.turn_on(entity_id=entity)
    else:
        switch.turn_off(entity_id=entity)


def _evaluate_and_apply_switch() -> None:
    now = datetime.now()
    avg = _avg_forecast_temp()
    if avg is None:
        log.warning(
            f"shelly_floor_heating: no forecast temp "
            f"(forecast_sensor={_forecast_sensor_entity()!r}) — leaving switch unchanged"
        )
        return
    hours = floor_heating_hours_from_temp(avg)
    if hours >= MAX_HOURS:
        on = True
        n_intervals = cheap_hours_to_interval_count(hours)
        reason = "always-on (extreme cold)"
    elif hours <= 0:
        on = False
        n_intervals = 0
        reason = "always-off (warm)"
    else:
        cheapest = build_cheapest_intervals(_price_rows(), hours)
        n_intervals = len(cheapest)
        on = is_interval_among_cheapest(now, cheapest)
        reason = "cheapest intervals"
    log.warning(
        f"shelly_floor_heating: now={format_interval_key(interval_start_key(now))} "
        f"avg_temp={avg:.1f}C -> {hours:.1f} h ({n_intervals} intervals), "
        f"{reason}, switch_on={on}"
    )
    _apply_switch(on)


@time_trigger("startup")
def shelly_floor_heating_startup():
    avg = _avg_forecast_temp()
    hours = _heated_hours()
    log.warning(
        f"shelly_floor_heating: app loaded, forecast_sensor={_forecast_sensor_entity()!r}, "
        f"avg_temp={avg}, heated_hours={hours}, config={_cfg()}"
    )
    _evaluate_and_apply_switch()


@time_trigger("cron(0,15,30,45 * * * *)")
def shelly_floor_heating_tick():
    """At each 15-minute boundary, set switch according to forecast-driven plan."""
    _evaluate_and_apply_switch()


@time_trigger("cron(0 6,14 * * *)")
def shelly_floor_heating_recompute():
    """Recompute plan after forecast/Nordpool refresh (06:00 and ~14:00)."""
    _evaluate_and_apply_switch()


@service
def shelly_floor_heating_apply_now():
    """Force evaluation now (Developer Tools)."""
    _evaluate_and_apply_switch()


@service
def shelly_floor_heating_show_plan():
    """Log today's forecast, heated hours, and cheapest intervals (Developer Tools)."""
    avg = _avg_forecast_temp()
    if avg is None:
        log.warning(
            f"shelly_floor_heating: no forecast temp "
            f"(forecast_sensor={_forecast_sensor_entity()!r})"
        )
        return
    hours = floor_heating_hours_from_temp(avg)
    if hours >= MAX_HOURS:
        log.warning(
            f"shelly_floor_heating: avg_temp={avg:.1f}C -> always on (24 h)"
        )
        return
    if hours <= 0:
        log.warning(
            f"shelly_floor_heating: avg_temp={avg:.1f}C -> always off (0 h)"
        )
        return
    slots = build_cheapest_interval_slots(_price_rows(), hours)
    log.warning(
        f"shelly_floor_heating: avg_temp={avg:.1f}C -> {hours:.1f} heated hours "
        f"({len(slots)} intervals), sensor={_nordpool_sensor_entity()!r}, "
        f"{nordpool_diagnostics(_nordpool_attrs())}:\n{format_interval_plan(slots)}"
    )
