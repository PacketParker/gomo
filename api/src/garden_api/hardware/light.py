"""Grow light on a hardware PWM channel, driven through the kernel's sysfs interface.

Requires the ``pwm`` device-tree overlay (``dtoverlay=pwm,pin=18,func=2``).
The PWM peripheral runs without the CPU or a daemon. The light keeps its
brightness when the service restarts.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

_PERMISSION_WAIT_SECONDS = 1.0


class PwmLight:
    def __init__(self, chip: str | Path, channel: int, frequency_hz: int) -> None:
        chip = Path(chip)
        self._dir = chip / f"pwm{channel}"
        if not self._dir.is_dir():
            _write(chip / "export", channel)
        _wait_until_writable(self._dir / "duty_cycle")

        self._period_ns = round(1e9 / frequency_hz)
        self._lock = threading.Lock()
        self._level = self._resume_or_reset()

    @property
    def level(self) -> float:
        return self._level

    def set_level(self, level: float) -> float:
        """Set brightness as a percentage (0-100)."""
        with self._lock:
            _write(self._dir / "duty_cycle", round(self._period_ns * level / 100))
            self._level = level
        return level

    def _resume_or_reset(self) -> float:
        """Keep the current brightness if the channel already runs at this
        frequency, for example after a service restart. This prevents a blink."""
        if _read(self._dir / "period") == self._period_ns and _read(self._dir / "enable") == 1:
            return round((_read(self._dir / "duty_cycle") or 0) * 100 / self._period_ns)
        _write(self._dir / "duty_cycle", 0)  # must not exceed the new period
        _write(self._dir / "period", self._period_ns)
        _write(self._dir / "enable", 1)
        return 0


def _wait_until_writable(path: Path) -> None:
    """udev gives group access to a newly exported channel asynchronously."""
    deadline = time.monotonic() + _PERMISSION_WAIT_SECONDS
    while not os.access(path, os.W_OK) and time.monotonic() < deadline:
        time.sleep(0.02)


def _write(path: Path, value: int) -> None:
    path.write_text(str(value))


def _read(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None
