"""Water pump on a GPIO pin, either on or off.

"On" drives the pin with software PWM at a fixed ``duty``. The default is 70%.
At lower duties the pump spins but does not lift water up the tower.

The PWM thread runs only while the pump is on. Each start sets an auto-off
timer, so the pump never runs longer than ``max_run_seconds``.
"""

from __future__ import annotations

import math
import threading
import time

from .gpio import Gpio


class Pump:
    def __init__(
        self, gpio: Gpio, pin: int, frequency_hz: int, duty: int, max_run_seconds: float
    ) -> None:
        self._gpio = gpio
        self._pin = pin
        self._period = 1 / frequency_hz
        self._duty = duty
        self.max_run_seconds = max_run_seconds
        self._on = False
        self._stops_at = 0.0  # time.monotonic() of the scheduled auto-off
        self._cond = threading.Condition()
        self._pwm_thread: threading.Thread | None = None
        self._stop_timer: threading.Timer | None = None

        gpio.write(pin, False)
        gpio.set_output(pin)

    @property
    def is_on(self) -> bool:
        return self._on

    @property
    def seconds_left(self) -> int:
        """Whole seconds until the auto-off, or 0 when the pump is off."""
        if not self._on:
            return 0
        return max(0, math.ceil(self._stops_at - time.monotonic()))

    @property
    def pwm_active(self) -> bool:
        return self._pwm_thread is not None

    def on(self, run_seconds: float | None = None) -> float:
        """Start the pump, or keep it running. It stops automatically after
        ``run_seconds``, capped at ``max_run_seconds``. Return the run time."""
        seconds = min(run_seconds or self.max_run_seconds, self.max_run_seconds)
        with self._cond:
            self._on = True
            if self._duty == 100:
                self._gpio.write(self._pin, True)
            elif self._pwm_thread is None:
                self._pwm_thread = threading.Thread(target=self._run_pwm, daemon=True)
                self._pwm_thread.start()
            self._stops_at = time.monotonic() + seconds
            self._replace_stop_timer(threading.Timer(seconds, self.off))
        return seconds

    def off(self) -> None:
        with self._cond:
            self._on = False
            self._gpio.write(self._pin, False)
            self._cond.notify()  # wake the PWM thread so it exits now
            self._replace_stop_timer(None)

    def _replace_stop_timer(self, timer: threading.Timer | None) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
        self._stop_timer = timer
        if timer is not None:
            timer.daemon = True
            timer.start()

    def _run_pwm(self) -> None:
        # All pin writes occur while the lock is held. off() sets the pin low,
        # so this loop only exits when the pump is off.
        high_time = self._period * self._duty / 100
        with self._cond:
            while self._on:
                self._gpio.write(self._pin, True)
                self._cond.wait(high_time)
                if not self._on:
                    break
                self._gpio.write(self._pin, False)
                self._cond.wait(self._period - high_time)
            self._pwm_thread = None


def force_pin_low(gpiomem: str, pin: int) -> None:
    """Set the pump pin low without other state. systemd runs this after the
    service stops or crashes."""
    gpio = Gpio(gpiomem)
    try:
        gpio.write(pin, False)
        gpio.set_output(pin)
    finally:
        gpio.close()
