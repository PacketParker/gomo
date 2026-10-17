# gomo API (garden-api)

The Raspberry Pi half of [gomo](..): a REST API on the Gardyn's Pi that the
[web app](../web) (or anything else that speaks HTTP) calls. It replaces the
[garden-of-eden](https://github.com/iot-root/garden-of-eden) API and is pure
standard library at runtime: no Flask, no gpiozero, no `pigpiod`, no MQTT
service, no cron jobs.

The Pi only does what the hardware strictly needs. Scheduling, the dashboard
and reminders live in the web app.

| Device | How it's driven | Idle cost |
|---|---|---|
| Light | Hardware PWM on GPIO18 via `/sys/class/pwm` | none; the PWM peripheral runs by itself |
| Pump | On/off at a fixed 70% PWM duty via `/dev/gpiomem`; PWM thread only while on | none |
| Power | INA219 registers over `/dev/i2c-1`, read on request (~1 ms) | none |
| Water level | HC-SR04 ping on request (~150 ms for 5 samples) | none |
| Camera | `fswebcam` per request, JPEG piped straight back | none |

## API

Light, sensor and camera paths match garden-of-eden. The pump is on/off only.

```
GET  /light/brightness                      {"value": 0-100}
POST /light/on | /light/off                 {"value": ...}
POST /light/brightness   {"value": 70}      {"value": 70}
GET  /pump                                  {"on": true, "seconds_left": 287}
POST /pump/on                               {"on": true, "seconds": 900}   # runs until the cap
POST /pump/on            {"seconds": 300}   {"on": true, "seconds": 300}
POST /pump/off                              {"on": false}
GET  /pump/stats                            {"BusVoltage", "BusCurrent", "Power", "ShuntVoltage"}  (V, mA, mW, mV)
GET  /distance                              {"distance": cm, "gallons": ...}
GET  /camera/upper | /camera/lower          image/jpeg
```

Errors are JSON `{"error": ...}`:

| Status | Meaning |
|---|---|
| 400 | Bad input |
| 401 | Missing or wrong `X-API-Key` |
| 404 | Unknown path |
| 405 | Wrong method for a known path |
| 413 | Request body over 4 KB |
| 503 | Hardware missing or failing |
| 500 | Unexpected error; details are logged, never returned |

**Pump safety stays on the Pi.** "On" always drives the pump at `PUMP_DUTY`
(default 70%, the lowest tested duty that lifts water up the tower; 30% spins
the pump without moving water), and every start arms an auto-off, at most
`MAX_PUMP_RUN_SECONDS` (default 900). If your scheduler
or the network dies mid-run, the pump still stops. systemd also forces the
pump pin low whenever the service stops or crashes.

## Layout

```
src/garden_api/
├── __main__.py        CLI entry point (`garden-api`, `garden-api --pump-off`)
├── config.py          Settings: frozen, validated, read from environment variables
├── garden.py          Builds the devices; missing hardware is logged, not fatal
├── api.py             Routes, input validation, response shapes (no HTTP details)
├── server.py          HTTP: auth, body limits, keep-alive (stdlib http.server)
├── tank.py            Distance -> gallons
├── errors.py
└── hardware/          One module per device, no HTTP knowledge
    ├── gpio.py        /dev/gpiomem register access
    ├── light.py       sysfs hardware PWM
    ├── pump.py        GPIO pump: on/off at a fixed duty, auto-off
    ├── power.py       INA219 over i2c-dev
    ├── ultrasonic.py  HC-SR04
    └── camera.py      fswebcam
install.sh             Sets up the Pi and installs the systemd service
deploy/                Example environment file
```

## Install on the Pi

Supports Pi Zero / Zero 2 / 3 / 4 (BCM283x GPIO registers), which covers
Gardyn hardware. Not Pi 5. Needs Python 3.9+.

Clone the repo and run the installer as the user the service should run as:

```bash
sudo apt install -y git
git clone https://git.pkrm.dev/gomo ~/gomo
~/gomo/api/install.sh
```

[`install.sh`](install.sh) enables hardware PWM on GPIO18 (adding the overlay
to `config.txt` only if it's missing) and I2C, installs `fswebcam` and uv,
adds you to the `gpio`, `i2c` and `video` groups, copies the example
`/etc/garden-api.env` if there isn't one, and writes a systemd unit that runs
as you from `~/gomo/api`. It's safe to re-run.

Check it:

```bash
curl http://localhost:5000/light/brightness
journalctl -u garden-api      # lists any hardware that failed to initialize
```

To update: `cd ~/gomo && git pull && sudo systemctl restart garden-api`.

`pigpiod` must stay off. It takes over the PWM hardware that the light uses.

## Configuration

All settings are environment variables, read from `/etc/garden-api.env` by
systemd. See [`deploy/garden-api.env`](deploy/garden-api.env) for the full
list with defaults. Invalid values stop startup with a clear message.

## Scheduling off-Pi

The [web app](../web) runs the schedule for you. Without it, anything that can
send an HTTP request can do the job. For example, crontab on another machine:

```cron
0 6   * * *  curl -s -X POST -d '{"value":70}' http://gardyn.local:5000/light/brightness
0 22  * * *  curl -s -X POST http://gardyn.local:5000/light/off
0 8,16 * * * curl -s -X POST -d '{"seconds":300}' http://gardyn.local:5000/pump/on
```

Since the Pi no longer schedules anything, lights and watering depend on that
machine being up. After a Pi reboot the light comes up off until the next
scheduled call. Re-sending the current state every few minutes avoids that.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy              # strict
```
