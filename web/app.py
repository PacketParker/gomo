"""Status page and controls for a Gardyn running garden-api.

The page is static HTML; a small script keeps it live over Server-Sent Events.
While at least one browser is listening, a single background thread polls the
API and pushes a snapshot to every listener. Buttons post in the background and
trigger an immediate poll, so changes show up at once. The light/pump
schedule runs here too (see schedule.py), around the clock, and so does
grow-cycle tracking with its reminders (see cycle.py).

Environment: GARDEN_URL, GARDEN_API_KEY, TANK_GALLONS (5), WATER_LOW_GALLONS
(1.5; 0 disables the warning), POLL_SECONDS (2), WATER_POLL_SECONDS (30),
SCHEDULE_FILE and CYCLE_FILE (schedule.json and cycle.json next to this file).
"""

import datetime as dt
import json
import os
import queue
import threading
import time

import requests
from flask import Flask, Response, abort, render_template, request

from cycle import Cycle
from schedule import PRESETS, Scheduler

API = os.getenv("GARDEN_URL", "http://gardyn.local:5000").rstrip("/")
HEADERS = {"X-API-Key": key} if (key := os.getenv("GARDEN_API_KEY")) else {}
TANK_GALLONS = float(os.getenv("TANK_GALLONS", "5"))
WATER_LOW_GALLONS = float(os.getenv("WATER_LOW_GALLONS", "1.5"))
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "2"))
WATER_POLL_SECONDS = float(os.getenv("WATER_POLL_SECONDS", "30"))
HERE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_FILE = os.getenv("SCHEDULE_FILE", os.path.join(HERE, "schedule.json"))
CYCLE_FILE = os.getenv("CYCLE_FILE", os.path.join(HERE, "cycle.json"))

app = Flask(__name__)


@app.before_request
def same_origin_posts_only():
    if request.method == "POST" and request.headers.get("Sec-Fetch-Site", "same-origin") not in (
        "same-origin",
        "none",
    ):
        abort(403)  # another site's form must not be able to switch the pump on


@app.after_request
def no_framing(response):
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"  # no clickjacking
    return response


def fetch(path):
    try:
        response = requests.get(API + path, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def send(path, body=None):
    """POST to the API. Returns None on success, or an error message."""
    try:
        response = requests.post(API + path, json=body, headers=HEADERS, timeout=10)
        return None if response.ok else response.json().get("error", "Request failed")
    except (requests.RequestException, ValueError):
        return "The garden didn't respond"


def water_reading():
    water = fetch("/distance")
    if not water or water.get("gallons") is None:
        return None
    percent = round(min(100, max(0, water["gallons"] / TANK_GALLONS * 100)))
    low = bool(WATER_LOW_GALLONS) and water["gallons"] <= WATER_LOW_GALLONS
    return {**water, "percent": percent, "low": low}


class Live:
    """Polls the API only while someone is listening and fans out snapshots."""

    def __init__(self):
        self._lock = threading.Lock()
        self._listeners = set()
        self._running = False
        self._snapshot = None
        self._wake = threading.Event()

    def refresh(self):
        self._wake.set()

    def listen(self):
        """Yield JSON snapshots: the latest one right away, then each update."""
        updates = queue.Queue(maxsize=1)
        with self._lock:
            self._listeners.add(updates)
            snapshot = self._snapshot
            if not self._running:
                self._running = True
                threading.Thread(target=self._poll, daemon=True).start()
        try:
            if snapshot:
                yield snapshot
            while True:
                try:
                    yield updates.get(timeout=15)
                except queue.Empty:
                    yield None  # keep-alive, and notices clients that went away
        finally:
            with self._lock:
                self._listeners.discard(updates)

    def _poll(self):
        water, water_due = None, 0.0
        while True:
            with self._lock:
                if not self._listeners:
                    self._running, self._snapshot = False, None
                    return
            if time.monotonic() >= water_due:
                water, water_due = water_reading(), time.monotonic() + WATER_POLL_SECONDS
            snapshot = json.dumps(
                {
                    "light": fetch("/light/brightness"),
                    "pump": fetch("/pump"),
                    "power": fetch("/pump/stats"),
                    "water": water,
                    "schedule": scheduler.status(),
                    "cycle": cycle.status(),
                }
            )
            with self._lock:
                self._snapshot = snapshot
                for updates in self._listeners:
                    try:
                        updates.get_nowait()  # a slow client only needs the newest
                    except queue.Empty:
                        pass
                    updates.put_nowait(snapshot)
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()


live = Live()
scheduler = Scheduler(SCHEDULE_FILE, send=lambda *a: send(*a) is None, on_change=live.refresh)
scheduler.start()
cycle = Cycle(CYCLE_FILE)


@app.get("/")
def index():
    today = dt.date.today()
    return render_template(
        "page.html",
        presets=PRESETS,
        today=today.isoformat(),
        vacation_until=(today + dt.timedelta(days=14)).isoformat(),
    )


@app.get("/events")
def events():
    stream = (f"data: {s}\n\n" if s else ": ping\n\n" for s in live.listen())
    return Response(
        stream,
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/<any(light, pump):device>")
def control(device):
    form = request.form
    try:
        if device == "light":
            path, body = "/light/brightness", {"value": int(form["value"])}
        elif "seconds" in form:
            path, body = "/pump/on", {"seconds": int(form["seconds"])}
        else:
            path, body = {"on": "/pump/on", "off": "/pump/off"}[form["pump"]], None
    except (KeyError, ValueError):
        return {"error": "Invalid request"}, 400

    if error := send(path, body):
        return {"error": error}, 502
    live.refresh()
    return "", 204


@app.post("/schedule")
def set_schedule():
    form = request.form
    try:
        if "enabled" in form:
            scheduler.set_enabled(form["enabled"] == "on")
        else:
            scheduler.choose(form["preset"], until=form.get("until"))
    except KeyError:
        return {"error": "Invalid request"}, 400
    except ValueError as exc:
        return {"error": str(exc)}, 400
    return "", 204


@app.post("/cycle")
def set_cycle():
    form = request.form
    actions = {
        "new": lambda: cycle.start(form.get("started")),
        "set": lambda: cycle.set_start(form.get("started")),
        "done": lambda: cycle.mark_done(form.get("key")),
    }
    try:
        actions[form.get("action")]()
    except KeyError:
        return {"error": "Invalid request"}, 400
    except ValueError as exc:
        return {"error": str(exc)}, 400
    live.refresh()
    return "", 204


@app.get("/photo/<any(upper, lower):camera>")
def photo(camera):
    try:
        response = requests.get(f"{API}/camera/{camera}", headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return "", 503
    return Response(response.content, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8080")), threaded=True)
