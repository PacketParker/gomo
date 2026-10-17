# Garden

Status page and controls for a Gardyn running [garden-api](../api).
Flask, plain HTML/CSS, and a small script for live updates.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py      # http://localhost:8080
```

| Variable             | Default                     |                                          |
|----------------------|-----------------------------|------------------------------------------|
| `GARDEN_URL`         | `http://gardyn.local:5000`  | garden-api base URL                      |
| `GARDEN_API_KEY`     |                             | sent as `X-API-Key`                      |
| `TANK_GALLONS`       | `5`                         | for the fill bar                         |
| `WATER_LOW_GALLONS`  | `1.5`                       | warn at or below this; `0` to disable    |
| `POLL_SECONDS`       | `2`                         | how often light/pump/power refresh       |
| `WATER_POLL_SECONDS` | `30`                        | how often the water level refreshes      |
| `SCHEDULE_FILE`      | `schedule.json` (app dir)   | where the schedule choice is saved       |
| `CYCLE_FILE`         | `cycle.json` (app dir)      | where the grow cycle is saved            |
| `PORT` / `HOST`      | `8080` / `0.0.0.0`          |                                          |

How it works:

- **Live over Server-Sent Events** (`/events`). While at least one page is
  open, one background thread polls the API and pushes a snapshot to every
  browser. Nobody watching means no polling of the Pi.
- **The pump countdown ticks in the browser** and is corrected by each snapshot.
- **Buttons post in the background** and trigger an immediate poll, so the
  change shows at once without reloading anything. Errors appear in the
  section's header. Posts from other sites are refused.
- **The schedule runs here, not on the Pi or in cron.** Pick a preset
  (Germinate, Seedling, Vegetative, Flower, Night, or Vacation until a date,
  after which the previous preset resumes). A background thread sleeps until
  the next scheduled change (an on/off time, a pump run, midnight, or the next
  1% step of a fade), sets the light only when its scheduled level changes, so
  manual changes stick until the next one, and starts each pump run on time (up
  to 2 min late if the garden was unreachable). Times use this server's local
  time zone.
- **Grow cycle.** Start a cycle (or correct its start date) to see the day
  and stage, with reminders carried over from garden-of-eden: thin at day 14,
  check roots at day 21, harvest at day 35, and plant food 7 days after the
  start or the last feeding. Each reminder stays until marked done.
- **Photos are proxied**, so the API key never reaches the browser, and only
  refresh on a page reload.
- Behind nginx, response buffering must be off for `/events`; the app sends
  `X-Accel-Buffering: no`, which nginx honours.
