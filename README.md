# gomo — garden of my own

Control for a Gardyn hydroponic garden, in two parts: a small API on the
Gardyn's Raspberry Pi, and a companion web app on any other machine.

```
┌──────────── server / NAS / laptop ────────────┐          ┌──────── Gardyn Raspberry Pi ────────┐
│  web/  companion web app (Docker or Python)   │   HTTP   │  api/  garden-api                   │
│  status page, controls, schedule, grow cycle  │ ───────► │  light, pump, power, water, cameras │
└───────────────────────────────────────────────┘ X-API-Key└─────────────────────────────────────┘
```

The idea is to keep the Pi simple. It only drives the hardware and answers
requests: no scheduler, cron, MQTT or other daemons. Everything else runs in
the web app on a machine that's easier to update and look after.

| Part | Runs on | What it does |
|---|---|---|
| [`api/`](api) | Gardyn's Pi (systemd) | REST API for the light, the pump (on/off at a fixed duty, with an auto-off the Pi always enforces), power readings, water level and the two cameras. Python standard library only. |
| [`web/`](web) | Any server (Docker) | Live status page and controls, the light/pump schedule presets, and grow-cycle reminders. Talks only to the API. |

The web app is optional. The API is plain HTTP, so cron, Home Assistant or
a script can drive it instead (see [Scheduling off-Pi](api/README.md#scheduling-off-pi)).

## Quick start

1. **Install the API on the Pi.** Follow [api/README.md](api/README.md#install-on-the-pi).
   Then check it: `curl http://<pi>:5000/light/brightness`.
2. **Start the web app** on another machine. All it needs is the compose file;
   Docker builds the image from this repository:

   ```bash
   curl -O https://git.pkrm.dev/gomo/plain/web/compose.yaml
   GARDEN_URL=http://<pi-ip>:5000 TZ=America/Chicago docker compose up -d
   ```

   Open `http://<server>:8080`. See [web/README.md](web/README.md) for every
   setting and for running without Docker.

If you set `GARDEN_API_KEY` in the Pi's `/etc/garden-api.env`, set the same
value for the web app.

## Credit and license

Forked from [iot-root/garden-of-eden](https://github.com/iot-root/garden-of-eden);
its history is kept in this repository. The hardware details (pins, PWM
frequencies, sensor addresses) and the schedule presets and reminders come from
that project.

Licensed under the GNU General Public License v3.0, like the original. See
[LICENSE](LICENSE).
