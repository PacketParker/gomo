"""HC-SR04 ultrasonic sensor measuring the distance down to the water surface.

Measures only on request. There is no background polling.
"""

from __future__ import annotations

import threading
import time

from ..errors import HardwareUnavailable
from .gpio import Gpio

_TRIGGER_PULSE_SECONDS = 0.00001
_ECHO_TIMEOUT_SECONDS = 0.04  # longer than the sensor's ~38 ms "no echo" pulse
_SETTLE_SECONDS = 0.03  # lets echoes stop between pings
_HALF_SPEED_OF_SOUND_CM_S = 17150


class UltrasonicSensor:
    def __init__(self, gpio: Gpio, trigger_pin: int, echo_pin: int, samples: int) -> None:
        self._gpio = gpio
        self._trigger = trigger_pin
        self._echo = echo_pin
        self._samples = samples
        self._lock = threading.Lock()

        gpio.write(trigger_pin, False)
        gpio.set_output(trigger_pin)
        gpio.set_input(echo_pin)

    def measure_cm(self) -> float:
        """Median of several pings, in centimetres."""
        with self._lock:
            readings = []
            for i in range(self._samples):
                if i:
                    time.sleep(_SETTLE_SECONDS)
                distance = self._ping()
                if distance is not None:
                    readings.append(distance)
        if not readings:
            raise HardwareUnavailable("no echo from the water-level sensor")
        readings.sort()
        return round(readings[len(readings) // 2], 1)

    def _ping(self) -> float | None:
        self._gpio.write(self._trigger, True)
        time.sleep(_TRIGGER_PULSE_SECONDS)
        self._gpio.write(self._trigger, False)

        deadline = time.perf_counter() + _ECHO_TIMEOUT_SECONDS
        if not self._wait_for_echo(True, deadline):
            return None
        start = time.perf_counter()
        if not self._wait_for_echo(False, deadline):
            return None
        return (time.perf_counter() - start) * _HALF_SPEED_OF_SOUND_CM_S

    def _wait_for_echo(self, level: bool, deadline: float) -> bool:
        while self._gpio.read(self._echo) != level:
            if time.perf_counter() > deadline:
                return False
        return True
