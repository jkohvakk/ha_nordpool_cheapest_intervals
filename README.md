# ha_nordpool_cheapest_intervals

Home Assistant [pyscript](https://hacs-pyscript.readthedocs.io/) automation: turn Shelly switches **on** during the **cheapest 15-minute electricity intervals** each day, using [Nordpool](https://github.com/custom-components/nordpool) price data.

Config uses decimal **`cheap_hours`** (each `0.25` = one 15-minute slot; `1.75` = 7 intervals).

Develop on this machine with **Git**, **Cursor**, and **pytest**. Deploy to Home Assistant at `homeassistant.local` with a single script.

## Repository layout

```
ha_nordpool_cheapest_intervals/
├── pyscript/                              # deployed to HA /config/pyscript/
│   ├── modules/cheapest_intervals.py        # pure logic (unit-tested locally)
│   ├── apps/shelly_cheap_intervals/       # water heating (triggers + services)
│   ├── apps/shelly_car_charging/          # car charging (triggers + services)
│   ├── apps/shelly_floor_heating/         # floor heating (weather-driven hours)
│   └── config.yaml.example                # copy to configuration.yaml on HA
├── scripts/deploy.sh                      # rsync to Home Assistant
├── tests/                                 # pytest (no HA required)
└── .env.example                           # HA host/user for deploy
```

## Prerequisites on Home Assistant

1. **Pyscript** integration installed and enabled
2. **Nordpool** integration with a price sensor (note the entity ID)
3. **Shelly** switch working (note the entity ID)
4. **SSH** add-on (for `deploy.sh`) *or* copy files via Samba / File Editor

## One-time setup

### 1. Clone (other machines)

```bash
git clone https://github.com/jkohvakk/ha_nordpool_cheapest_intervals.git
cd ha_nordpool_cheapest_intervals
```

### 2. Local Python (tests only)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

### 3. Configure apps on Home Assistant

Add **timer** helpers for manual boost (UI: **Settings → Helpers → Timer**, or YAML). YAML-defined timers require a **full HA restart** before they appear in States.

```yaml
timer:
  water_heating_boost:
    name: Water heating boost
    duration: "06:00:00"
    restore: true
  car_charging_boost:
    name: Car charging boost
    duration: "06:00:00"
    restore: true
```

Add under **`configuration.yaml`** (or merge into your existing `pyscript:` section):

```yaml
pyscript:
  apps:
    shelly_cheap_intervals:
      nordpool_sensor: sensor.nordpool_new
      shelly_switch: switch.shellypro2_ec62608fe9dc_output_1
      cheap_hours: 1.75   # 7 x 15-minute intervals
      boost_timer: timer.water_heating_boost
      boost_duration: "06:00:00"

    shelly_car_charging:
      nordpool_sensor: sensor.nordpool_new
      shelly_switch: switch.shelly_car_charger
      cheap_hours: 7
      night_start: 22
      night_end: 7
      boost_timer: timer.car_charging_boost
      boost_duration: "06:00:00"

    shelly_floor_heating:
      nordpool_sensor: sensor.nordpool_new
      shelly_switch: switch.shelly_floor_heating
      forecast_sensor: sensor.daily_forecast_avg_c
```

#### Water heating (`shelly_cheap_intervals`)

| Key | Example | Description |
|-----|---------|-------------|
| `nordpool_sensor` | `sensor.nordpool_new` | Your Nordpool sensor |
| `shelly_switch` | `switch.shelly_outdoor_plug` | Switch to control |
| `cheap_hours` | `1.75` | Decimal hours of cheap intervals per day (`0.25` = one 15-min slot) |
| `boost_timer` | `timer.water_heating_boost` | Optional timer entity for manual boost |
| `boost_duration` | `"06:00:00"` | Default boost length when service omits `duration` |

#### Car charging (`shelly_car_charging`)

Switch on when **any** of: 7 cheapest hours, night window 22:00–07:00, or active boost.

| Key | Example | Description |
|-----|---------|-------------|
| `nordpool_sensor` | `sensor.nordpool_new` | Your Nordpool sensor |
| `shelly_switch` | `switch.shelly_car_charger` | Car charger switch |
| `cheap_hours` | `7` | Cheapest hours per day |
| `night_start` | `22` | Night window start hour (inclusive) |
| `night_end` | `7` | Night window end hour (exclusive) |
| `boost_timer` | `timer.car_charging_boost` | Optional timer for manual charging boost |
| `boost_duration` | `"06:00:00"` | Default boost length |

#### Floor heating (`shelly_floor_heating`)

Heated hours are derived from today's **average forecast temperature**:

| Avg temp | Heated hours |
|----------|--------------|
| ≤ −20 °C | 24 h (always on) |
| −10 °C | 18 h |
| 0 °C | 12 h |
| +10 °C | 6 h |
| ≥ +20 °C | 0 h (always off) |

Between those points the duration scales linearly. The cheapest intervals are then picked from Nordpool for that many hours.

| Key | Example | Description |
|-----|---------|-------------|
| `nordpool_sensor` | `sensor.nordpool_new` | Your Nordpool sensor |
| `shelly_switch` | `switch.shelly_floor_heating` | Floor heating switch |
| `forecast_sensor` | `sensor.daily_forecast_avg_c` | Sensor whose state is today's average forecast temperature (°C) |

##### Forecast average sensor (required)

Modern HA weather entities don't expose the hourly forecast as an attribute, so create a **template sensor** that calls `weather.get_forecasts` and averages today's hourly temperatures.

Replace `weather.forecast_koti` with your weather entity in **both** the `target: entity_id` and the `fc[...]` lookup — the response variable `fc` is keyed by the entity you target, so the two must match (a mismatch raises `UndefinedError: 'dict object' has no attribute ...`).

```yaml
template:
  - triggers:
      - trigger: homeassistant
        event: start
      - trigger: time_pattern
        hours: /1
    actions:
      - action: weather.get_forecasts
        data:
          type: hourly
        target:
          entity_id: weather.forecast_koti     # <- your weather entity
        response_variable: fc
    sensor:
      - name: Daily forecast avg C
        unique_id: daily_forecast_avg_c
        unit_of_measurement: "°C"
        state: >
          {% set ns = namespace(temps=[]) %}
          {% set fcl = fc['weather.forecast_koti'].forecast %}   {# <- same entity #}
          {% for e in fcl %}
            {% if as_datetime(e.datetime).date() == now().date() %}
              {% set ns.temps = ns.temps + [e.temperature | float] %}
            {% endif %}
          {% endfor %}
          {% if ns.temps | count > 0 %}
            {{ (ns.temps | sum / ns.temps | count) | round(2) }}
          {% endif %}
```

This produces `sensor.daily_forecast_avg_c`. After saving, reload via **Developer Tools → Actions → `homeassistant.reload_all`** and verify it has a numeric value under **Developer Tools → States** before relying on floor heating.

Find entity IDs under **Developer Tools → States**.

### 4. Deploy access

```bash
cp .env.example .env
# edit HA_HOST / HA_USER if needed
chmod +x scripts/deploy.sh
```

Ensure SSH works, e.g.:

```bash
ssh hassio@homeassistant.local
```

## Daily workflow

```bash
# 1. Edit code in Cursor
# 2. Run tests
pytest -v

# 3. Deploy to Home Assistant
./scripts/deploy.sh

# 4. Verify in HA
#    Developer Tools → Actions → pyscript.shelly_cheap_intervals_show_cheapest
#    Developer Tools → Actions → pyscript.shelly_cheap_intervals_apply_now
```

Pyscript **auto-reloads** when files under `/config/pyscript/` change (no manual reload needed in normal use).

## Services

### Water heating

| Service | Purpose |
|---------|---------|
| `pyscript.shelly_cheap_intervals_apply_now` | Evaluate plan and set switch now |
| `pyscript.shelly_cheap_intervals_show_cheapest` | Log today's cheapest 15-min intervals with prices |
| `pyscript.shelly_cheap_intervals_boost_start` | Turn switch on and start timed boost (`duration` optional) |
| `pyscript.shelly_cheap_intervals_boost_stop` | Cancel boost and re-evaluate switch from Nordpool plan |

### Car charging

| Service | Purpose |
|---------|---------|
| `pyscript.shelly_car_charging_apply_now` | Evaluate plan and set switch now |
| `pyscript.shelly_car_charging_show_plan` | Log cheapest intervals and night window |
| `pyscript.shelly_car_charging_boost_start` | Turn switch on and start timed boost (`duration` optional) |
| `pyscript.shelly_car_charging_boost_stop` | Cancel boost and re-evaluate switch from plan |

### Floor heating

| Service | Purpose |
|---------|---------|
| `pyscript.shelly_floor_heating_apply_now` | Evaluate plan and set switch now |
| `pyscript.shelly_floor_heating_show_plan` | Log avg forecast temp, heated hours, and cheapest intervals |

## Manual boost (dashboard)

Use **`perform-action`** or **`call-service`** syntax (depends on your HA version). A **vertical-stack** with two conditional cards (one for timer active, one for idle) is more reliable than a single `card_else` conditional.

### Water heating boost buttons

```yaml
type: vertical-stack
cards:
  - type: conditional
    conditions:
      - condition: state
        entity: timer.water_heating_boost
        state: active
    card:
      type: button
      name: Stop boost
      icon: mdi:stop-circle
      tap_action:
        action: perform-action
        perform_action: pyscript.shelly_cheap_intervals_boost_stop

  - type: conditional
    conditions:
      - condition: state
        entity: timer.water_heating_boost
        state: idle
    card:
      type: button
      name: Heat 6h
      icon: mdi:water-boiler
      tap_action:
        action: perform-action
        perform_action: pyscript.shelly_cheap_intervals_boost_start
        data:
          duration: "06:00:00"
```

### Car charging boost buttons

Same pattern with `timer.car_charging_boost` and `pyscript.shelly_car_charging_boost_*` services.

While boost is active, the switch stays **on** even outside cheap intervals / night window. When boost ends, normal scheduling resumes.

## Triggers

| App | Trigger | When |
|-----|---------|------|
| Water heating | Every 15 minutes | Switch on/off based on plan or boost |
| Water heating | Boost timer finishes | Re-evaluate switch immediately |
| Water heating | 14:00 cron | Log plan after Nordpool refresh |
| Car charging | Every 15 minutes | Switch on/off based on cheapest hours, night window, or boost |
| Car charging | Boost timer finishes | Re-evaluate switch immediately |
| Car charging | 14:00 cron | Log plan after Nordpool refresh |
| Floor heating | Every 15 minutes | Switch on/off based on weather-driven heated hours |
| Floor heating | 06:00 and 14:00 cron | Recompute plan after forecast/Nordpool refresh |

## Optional: Jupyter live debugging

If you use the [pyscript Jupyter kernel](https://github.com/craigbarratt/hass-pyscript-jupyter), keep `pyscript.conf` **local only** (listed in `.gitignore`).

## GitHub

Remote: [https://github.com/jkohvakk/ha_nordpool_cheapest_intervals](https://github.com/jkohvakk/ha_nordpool_cheapest_intervals)

```bash
git add -A && git commit -m "Describe change" && git push
```

**Do not commit** `.env`, access tokens, or `pyscript.conf`.

## Migrating from `ha_nordpool_cheapest_hours`

1. Rename the GitHub repository (Settings → General → Repository name).
2. Update `git remote set-url origin git@github.com:jkohvakk/ha_nordpool_cheapest_intervals.git`
3. On HA, rename app in `configuration.yaml`: `shelly_cheap_hours` → `shelly_cheap_intervals`
4. Deploy and remove old `/config/pyscript/apps/shelly_cheap_hours/` on HA
5. Call **`pyscript.reload`**

Old service names (`pyscript.shelly_cheap_hours_*`) no longer exist.
