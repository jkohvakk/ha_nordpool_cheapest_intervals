# ha_nordpool_cheapest_intervals

Home Assistant [pyscript](https://hacs-pyscript.readthedocs.io/) automation: turn Shelly switches **on** during the **cheapest 15-minute electricity intervals** each day, using [Nordpool](https://github.com/custom-components/nordpool) price data.

Config uses decimal **`cheap_hours`** (each `0.25` = one 15-minute slot; `1.75` = 7 intervals).

Develop on this machine with **Git**, **Cursor**, and **pytest**. Deploy to Home Assistant at `homeassistant.local` with a single script.

## Repository layout

```
ha_nordpool_cheapest_intervals/
├── pyscript/                              # deployed to HA /config/pyscript/
│   ├── modules/cheapest_intervals.py        # pure logic (unit-tested locally)
│   ├── apps/shelly_cheap_intervals/       # pyscript app (triggers + services)
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

### 3. Configure the app on Home Assistant

Add a **timer** helper for manual boost (UI: **Settings → Helpers → Timer**, or YAML):

```yaml
timer:
  water_heating_boost:
    name: Water heating boost
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
```

| Key | Example | Description |
|-----|---------|-------------|
| `nordpool_sensor` | `sensor.nordpool_new` | Your Nordpool sensor |
| `shelly_switch` | `switch.shelly_outdoor_plug` | Switch to control |
| `cheap_hours` | `1.75` | Decimal hours of cheap intervals per day (`0.25` = one 15-min slot) |
| `boost_timer` | `timer.water_heating_boost` | Optional timer entity for manual boost |
| `boost_duration` | `"06:00:00"` | Default boost length when service omits `duration` |

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

| Service | Purpose |
|---------|---------|
| `pyscript.shelly_cheap_intervals_apply_now` | Evaluate plan and set switch now |
| `pyscript.shelly_cheap_intervals_show_cheapest` | Log today's cheapest 15-min intervals with prices |
| `pyscript.shelly_cheap_intervals_boost_start` | Turn switch on and start timed boost (`duration` optional, default from config) |
| `pyscript.shelly_cheap_intervals_boost_stop` | Cancel boost and re-evaluate switch from Nordpool plan |

## Manual boost (dashboard)

When daily cheap slots are not enough (e.g. after washing dogs), start a timed boost from your dashboard:

```yaml
type: button
name: Heat 6h
icon: mdi:water-boiler
tap_action:
  action: call-service
  service: pyscript.shelly_cheap_intervals_boost_start
  data:
    duration: "06:00:00"
```

Add a second button for **Stop boost** calling `pyscript.shelly_cheap_intervals_boost_stop`, and show `timer.water_heating_boost` on the dashboard to see remaining time.

While boost is active, the switch stays **on** even outside cheap intervals. When the timer expires, normal Nordpool scheduling resumes (switch stays on only if the current interval is still in today's plan).

## Triggers

| Trigger | When |
|---------|------|
| Every 15 minutes (`:00`, `:15`, `:30`, `:45`) | Switch on/off based on plan or active boost |
| Boost timer finishes | Re-evaluate switch immediately |
| 14:00 cron | Log plan after Nordpool refresh (~14:00 Finnish time) |

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
