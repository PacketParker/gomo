"""Grow-cycle tracking and reminders, carried over from garden-of-eden.

A cycle is a start date. One-off reminders come due on a set day of the cycle
and stay until marked done; plant food comes due every FEED_EVERY_DAYS since
the cycle started or the plants were last fed. The stage follows the day count.
"""

import datetime as dt
import threading

from store import load_json, save_json

REMINDERS = {  # key: (day of the cycle, label)
    "thin": (14, "Thin the seedlings"),
    "roots": (21, "Check the roots"),
    "harvest": (35, "Harvest or trim"),
}
FEED = "feed"
FEED_LABEL = "Add plant food"
FEED_EVERY_DAYS = 7
STAGES = ((35, "Harvest"), (21, "Root check"), (14, "Thinning"), (0, "Germination"))


class Cycle:
    def __init__(self, path):
        self._path = path
        self._lock = threading.Lock()
        self._state = load_json(path, {"started": None, "done": [], "fed": None})

    def start(self, started):
        """Begin a new cycle: every reminder starts fresh."""
        self._update(started=_past_date(started).isoformat(), done=[], fed=None)

    def set_start(self, started):
        """Correct the current cycle's start date, keeping what's been done."""
        self._update(started=_past_date(started).isoformat())

    def mark_done(self, key):
        if key == FEED:
            self._update(fed=dt.date.today().isoformat())
        elif key in REMINDERS:
            with self._lock:
                done = sorted({*self._state["done"], key})
            self._update(done=done)
        else:
            raise ValueError("Unknown reminder")

    def status(self, today=None):
        today = today or dt.date.today()
        with self._lock:
            state = dict(self._state)
        if not state["started"]:
            return {"started": None, "due": []}

        started = dt.date.fromisoformat(state["started"])
        day = (today - started).days
        last_fed = dt.date.fromisoformat(state["fed"]) if state["fed"] else started
        feed_day = (last_fed - started).days + FEED_EVERY_DAYS

        due, upcoming = [], []  # upcoming: (days until, label)
        for key, (on_day, label) in REMINDERS.items():
            if key in state["done"]:
                continue
            if day >= on_day:
                due.append((key, label))
            else:
                upcoming.append((on_day - day, label))
        if day >= feed_day:
            due.append((FEED, FEED_LABEL))
        else:
            upcoming.append((feed_day - day, FEED_LABEL))

        soonest = min(upcoming, default=None)
        return {
            "started": state["started"],
            "day": day,
            "stage": next(label for on_day, label in STAGES if day >= on_day),
            "due": [{"key": key, "label": label} for key, label in due],
            "next": f"{soonest[1]} in {soonest[0]} day{'s' * (soonest[0] != 1)}" if soonest else None,
        }

    def _update(self, **changes):
        with self._lock:
            self._state.update(changes)
            save_json(self._path, self._state)


def _past_date(value):
    try:
        date = dt.date.fromisoformat(value or "")
    except ValueError:
        raise ValueError("Pick a start date") from None
    if date > dt.date.today():
        raise ValueError("The start date can't be in the future")
    return date
