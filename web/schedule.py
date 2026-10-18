"""Light and pump schedule, run by this app in a background thread (no cron).

The presets carry over garden-of-eden's values. The scheduler works out what
the light should be right now (with the sunrise and sunset fade) and sends it
only when that changes. A manual light change holds until the next on or off
time. Each pump run is started at its time, and up to two minutes late if the
garden was briefly unreachable. Between changes the thread sleeps until the
next one is due: an on/off time, a pump run, midnight, or the next 1% step of a
fade. The choice lives in a small JSON file so it survives restarts. Times are
this server's local time.
"""

import datetime as dt
import threading
from dataclasses import dataclass

from store import load_json, save_json

PUMP_GRACE_MINUTES = 2
RETRY_SECONDS = 30  # when the garden didn't answer
MAX_SLEEP_SECONDS = 3600  # re-check hourly so clock changes can't skip an event
DAY = 24 * 60


@dataclass(frozen=True)
class Preset:
    label: str
    light_on: str
    light_off: str
    brightness: int
    fade_minutes: int
    pump_times: tuple[str, ...]
    pump_minutes: int


PRESETS = {
    "germinate": Preset("Germinate", "06:00", "22:00", 30, 15, ("06:00", "12:00", "18:00"), 3),
    "seedling": Preset("Seedling", "06:00", "22:00", 50, 15, ("00:00", "08:00", "16:00"), 4),
    "vegetative": Preset("Vegetative", "06:00", "22:00", 80, 20, ("00:00", "08:00", "16:00"), 5),
    "flower": Preset("Flower", "07:00", "19:00", 100, 20, ("08:00", "14:00", "20:00"), 5),
    "night": Preset("Night", "23:00", "07:00", 80, 20, ("02:00", "05:00", "23:15"), 5),
    "vacation": Preset("Vacation", "10:00", "16:00", 50, 0, ("12:00",), 3),
}


def minute_of_day(hhmm):
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _light_position(preset, now_minutes):
    """Minutes since the light's on time, and the on-to-off window length.
    Windows may cross midnight."""
    since_on = (now_minutes - minute_of_day(preset.light_on)) % DAY
    window = (minute_of_day(preset.light_off) - minute_of_day(preset.light_on)) % DAY
    return since_on, window


def fading(preset, now_minutes):
    since_on, window = _light_position(preset, now_minutes)
    fade = preset.fade_minutes
    return since_on < min(fade, window) or 0 <= since_on - window < fade


def light_level(preset, now_minutes):
    """Brightness the light should have at ``now_minutes`` past midnight.
    The fade starts at the on and off times."""
    since_on, window = _light_position(preset, now_minutes)
    fade = preset.fade_minutes
    if since_on < min(fade, window):
        return round(preset.brightness * since_on / fade)
    if since_on < window:
        return preset.brightness
    if since_on - window < fade:
        return round(preset.brightness * (1 - (since_on - window) / fade))
    return 0


def last_light_switch(preset, now):
    """The most recent on or off time, as a datetime."""
    times = []
    for hhmm in (preset.light_on, preset.light_off):
        hours, minutes = map(int, hhmm.split(":"))
        t = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        times.append(t if t <= now else t - dt.timedelta(days=1))
    return max(times)


def seconds_until_next_change(preset, now, follow_fade=True):
    """Seconds until the next action. During a fade that is one 1% step,
    unless the light is held. Otherwise it is just after the next on/off time,
    pump run or midnight."""
    now_seconds = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
    if follow_fade and fading(preset, now_seconds / 60):
        return preset.fade_minutes * 60 / preset.brightness
    events = (preset.light_on, preset.light_off, *preset.pump_times, "00:00")
    return 0.5 + min((minute_of_day(e) * 60 - now_seconds) % (DAY * 60) or DAY * 60 for e in events)


class Scheduler:
    def __init__(self, path, send, on_change):
        """``send(path, body)`` posts to the garden API and returns True on
        success; ``on_change()`` is called whenever the garden or the schedule
        changes, so open pages update."""
        self._path = path
        self._send = send
        self._on_change = on_change
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._state = self._load()
        self._sent_light = None
        self._held_since = None  # on/off time in effect when the light was set by hand
        self._started_runs = set()

    # -- settings

    def set_enabled(self, enabled):
        with self._lock:
            self._state["enabled"] = enabled
            self._changed()

    def choose(self, preset, until=None):
        if preset not in PRESETS:
            raise ValueError("Unknown preset")
        with self._lock:
            if preset == "vacation":
                end = dt.date.fromisoformat(until or "")
                if end < dt.date.today():
                    raise ValueError("Vacation must end today or later")
                if self._state["preset"] != "vacation":
                    self._state["resume"] = self._state["preset"]
                self._state["vacation_until"] = end.isoformat()
            self._state.update(preset=preset, enabled=True)
            self._changed()

    def hold_light(self):
        """Do not change a manually set light until its next on or off time."""
        with self._lock:
            preset = PRESETS[self._state["preset"]]
            self._held_since = last_light_switch(preset, dt.datetime.now())
            self._sent_light = None  # re-apply once the hold ends
        self._wake.set()  # recalculate the sleep without fade steps

    def status(self):
        with self._lock:
            state = dict(self._state)
        preset = PRESETS[state["preset"]]
        now = dt.datetime.now()
        now_minutes = now.hour * 60 + now.minute
        next_run = min(preset.pump_times, key=lambda t: (minute_of_day(t) - now_minutes) % DAY)
        fade = f", {preset.fade_minutes} min fade" if preset.fade_minutes else ""
        return {
            "enabled": state["enabled"],
            "preset": state["preset"],
            "label": preset.label,
            "until": state["vacation_until"] if state["preset"] == "vacation" else None,
            "light": f"{preset.light_on}–{preset.light_off} at {preset.brightness}%{fade}",
            "pump": f"{', '.join(sorted(preset.pump_times))} for {preset.pump_minutes} min",
            "next_watering": next_run,
        }

    # -- running

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            self._wake.wait(self.tick())  # woken early by any schedule change
            self._wake.clear()

    def tick(self, now=None):
        """Bring the garden in line with the schedule. Returns the seconds until
        anything needs doing again, or None while the schedule is off."""
        now = now or dt.datetime.now()
        with self._lock:
            self._end_vacation_if_over(now.date())
            if not self._state["enabled"]:
                self._sent_light = None  # re-apply the light when turned back on
                return None
            preset = PRESETS[self._state["preset"]]
            now_minutes = now.hour * 60 + now.minute + now.second / 60
            changed = failed = False

            held = self._held_since == last_light_switch(preset, now)
            if not held:
                self._held_since = None
            level = light_level(preset, now_minutes)
            if not held and level != self._sent_light:
                if self._send("/light/brightness", {"value": level}):
                    self._sent_light, changed = level, True
                else:
                    failed = True

            today = now.date().isoformat()
            self._started_runs = {run for run in self._started_runs if run.startswith(today)}
            for start in preset.pump_times:
                run = f"{today} {start}"
                late = (now_minutes - minute_of_day(start)) % DAY
                if late < PUMP_GRACE_MINUTES and run not in self._started_runs:
                    if self._send("/pump/on", {"seconds": preset.pump_minutes * 60}):
                        self._started_runs.add(run)
                        changed = True
                    else:
                        failed = True

            delay = seconds_until_next_change(preset, now, follow_fade=not held)
            if failed:
                delay = min(delay, RETRY_SECONDS)
        if changed:
            self._on_change()
        return min(delay, MAX_SLEEP_SECONDS)

    # -- internals

    def _end_vacation_if_over(self, today):
        until = self._state["vacation_until"]
        if self._state["preset"] == "vacation" and until and today > dt.date.fromisoformat(until):
            self._state.update(preset=self._state["resume"] or "vegetative", vacation_until=None)
            self._save()

    def _changed(self):
        """Persist, apply the new schedule right away, and update open pages."""
        self._save()
        self._sent_light = None
        self._held_since = None
        self._wake.set()
        self._on_change()

    def _load(self):
        defaults = {"enabled": False, "preset": "vegetative", "vacation_until": None, "resume": None}
        state = load_json(self._path, defaults)
        return state if state["preset"] in PRESETS else defaults

    def _save(self):
        save_json(self._path, self._state)
