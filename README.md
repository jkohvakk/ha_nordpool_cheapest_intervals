# ha_nordpool_cheapest_hours

Home Assistant [pyscript](https://hacs-pyscript.readthedocs.io/) automation: turn Shelly switches **on** during the **N cheapest electricity hours** each day, using [Nordpool](https://github.com/custom-components/nordpool) price data.

Develop on this machine with **Git**, **Cursor**, and **pytest**. Deploy to Home Assistant at `homeassistant.local` with a single script.

## Repository layout

```
ha_nordpool_cheapest_hours/
├── pyscript/                          # deployed to HA /config/pyscript/
│   ├── modules/cheapest_hours.py      # pure logic (unit-tested locally)
│   ├── apps/shelly_cheap_hours/       # pyscript app (triggers + services)
│   └── config.yaml.example            # copy to config.yaml on HA
├── scripts/deploy.sh                  # rsync to Home Assistant
├── tests/                             # pytest (no HA required)
└── .env.example                       # HA host/user for deploy
```

## Prerequisites on Home Assistant

1. **Pyscript** integration installed and enabled
2. **Nordpool** integration with a price sensor (note the entity ID)
3. **Shelly** switch working (note the entity ID)
4. **SSH** add-on (for `deploy.sh`) *or* copy files via Samba / File Editor

## One-time setup

### 1. Clone (other machines)

```bash
git clone https://github.com/jkohvakk/ha_nordpool_cheapest_hours.git
cd ha_nordpool_cheapest_hours
```

### 2. Local Python (tests only)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

### 3. Configure the app on Home Assistant

Copy `pyscript/config.yaml.example` to **`/config/pyscript/config.yaml`** on HA (merge with existing `pyscript:` section if you already have one). Set:

| Key | Example | Description |
|-----|---------|-------------|
| `nordpool_sensor` | `sensor.nordpool_kwh_fi_eur_3_10_022` | Your Nordpool sensor |
| `shelly_switch` | `switch.shelly_outdoor_plug` | Switch to control |
| `cheap_hours` | `4` | How many cheapest hours per day to run ON |

Find entity IDs under **Developer Tools → States**.

### 4. Deploy access

```bash
cp .env.example .env
# edit HA_HOST / HA_USER if needed
chmod +x scripts/deploy.sh
```

Ensure SSH works, e.g.:

```bash
ssh root@homeassistant.local
```

(Exact user/host depends on your SSH add-on.)

## Daily workflow

```bash
# 1. Edit code in Cursor
# 2. Run tests
pytest -v

# 3. Deploy to Home Assistant
./scripts/deploy.sh

# 4. Verify in HA
#    Developer Tools → Actions → pyscript.shelly_cheap_hours_show_plan
#    Developer Tools → Actions → pyscript.shelly_cheap_hours_apply_now
```

Pyscript **auto-reloads** when files under `/config/pyscript/` change (no manual reload needed in normal use).

## Services

| Service | Purpose |
|---------|---------|
| `pyscript.shelly_cheap_hours_apply_now` | Evaluate cheapest-hour plan and set switch now |
| `pyscript.shelly_cheap_hours_show_plan` | Log today's cheapest hours without changing switch |

## Triggers

| Trigger | When |
|---------|------|
| Hourly cron | Top of each hour — switch on/off based on plan |
| 14:00 cron | Log plan after Nordpool refresh (~14:00 Finnish time) |

## Optional: Jupyter live debugging

If you use the [pyscript Jupyter kernel](https://github.com/craigbarratt/hass-pyscript-jupyter), keep `pyscript.conf` **local only** (listed in `.gitignore`). Use notebooks to inspect live Nordpool attributes; keep source of truth in this repo.

## GitHub

Remote: [https://github.com/jkohvakk/ha_nordpool_cheapest_hours](https://github.com/jkohvakk/ha_nordpool_cheapest_hours)

```bash
git add -A && git commit -m "Describe change" && git push
```

**Do not commit** `.env`, access tokens, or `pyscript.conf`.

## Next steps

- Replace placeholder entity IDs in `config.yaml` on HA
- Run `./scripts/deploy.sh` once
- Call `pyscript.shelly_cheap_hours_show_plan` and check logs
- Refine rules (time windows, consecutive hours, multiple switches) in issues or with Cursor
