# gomo — garden of my own

A lean rework of [garden-of-eden](https://github.com/iot-root/garden-of-eden)
for Gardyn hydroponic gardens: the Pi only drives the hardware, and everything
else runs on a server.

| | |
|---|---|
| [`api/`](api) | **garden-api**: a small REST API on the Gardyn's Raspberry Pi. Light, pump (on/off at a fixed duty with auto-off), power, water level and cameras. Python standard library only; no daemons, cron or MQTT. |
| [`web/`](web) | **garden-web**: a status page and controls that run on a server. Live updates over Server-Sent Events, schedule presets, and grow-cycle reminders. Flask, HTML/CSS and a small script. |

See each directory's README for setup.

## Credit and license

Forked from [iot-root/garden-of-eden](https://github.com/iot-root/garden-of-eden);
its history is kept in this repository. The hardware details (pins, PWM
frequencies, sensor addresses) and the schedule presets and reminders come from
that project.

Licensed under the GNU General Public License v3.0, like the original. See
[LICENSE](LICENSE).
