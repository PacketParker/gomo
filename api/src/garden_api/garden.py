"""Builds the set of devices from settings.

Hardware that fails to initialize is logged and left as None, so the rest of
the API keeps working and the affected endpoints answer 503.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from .config import Settings
from .hardware.camera import Camera
from .hardware.gpio import Gpio
from .hardware.light import PwmLight
from .hardware.power import Ina219
from .hardware.pump import Pump
from .hardware.ultrasonic import UltrasonicSensor

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class Garden:
    light: PwmLight | None = None
    pump: Pump | None = None
    power: Ina219 | None = None
    water: UltrasonicSensor | None = None
    cameras: dict[str, Camera] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, s: Settings) -> Garden:
        gpio = _try("GPIO", lambda: Gpio(s.gpiomem))
        garden = cls(
            light=_try(
                "light",
                lambda: PwmLight(
                    s.light_pwm_chip, s.light_pwm_channel, s.light_frequency
                ),
            ),
            power=_try(
                "power monitor",
                lambda: Ina219(s.i2c_bus, s.ina219_address, s.shunt_ohms),
            ),
            cameras={
                "upper": Camera(
                    s.upper_camera_device,
                    s.camera_resolution,
                    s.camera_skip_frames,
                    s.fswebcam,
                ),
                "lower": Camera(
                    s.lower_camera_device,
                    s.camera_resolution,
                    s.camera_skip_frames,
                    s.fswebcam,
                ),
            },
        )
        if gpio is not None:
            garden.pump = _try(
                "pump",
                lambda: Pump(
                    gpio,
                    s.pump_pin,
                    s.pump_frequency,
                    s.pump_duty,
                    s.max_pump_run_seconds,
                ),
            )
            garden.water = _try(
                "water-level sensor",
                lambda: UltrasonicSensor(
                    gpio,
                    s.distance_trigger_pin,
                    s.distance_echo_pin,
                    s.distance_samples,
                ),
            )
        return garden

    def shutdown(self) -> None:
        """Put the hardware in a safe state. The pump must not run unattended."""
        if self.pump is not None:
            self.pump.off()


def _try(name: str, factory: Callable[[], T]) -> T | None:
    try:
        return factory()
    except Exception as exc:  # any failure means the device is not available
        logger.warning("%s unavailable: %s", name, exc)
        return None
