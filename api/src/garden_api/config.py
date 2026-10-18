"""Settings, read once from environment variables.

Each field maps to the upper-cased environment variable of the same name
(``pump_pin`` -> ``PUMP_PIN``). Unset or empty variables keep the default.
Integers accept hex (``INA219_ADDRESS=0x40``).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import Any

_PARSERS: dict[str, Callable[[str], object]] = {
    "int": lambda raw: int(raw, 0),
    "float": float,
    "str": str,
}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 5000
    garden_api_key: str = ""
    log_level: str = "INFO"

    gpiomem: str = "/dev/gpiomem"

    light_pwm_chip: str = "/sys/class/pwm/pwmchip0"
    light_pwm_channel: int = 0  # GPIO18 is PWM channel 0
    light_frequency: int = 8000

    pump_pin: int = 24
    pump_frequency: int = 50
    pump_duty: int = 70  # lowest tested duty that lifts water up the tower
    max_pump_run_seconds: int = 900

    i2c_bus: str = "/dev/i2c-1"
    ina219_address: int = 0x40
    shunt_ohms: float = 0.08

    distance_trigger_pin: int = 26
    distance_echo_pin: int = 19
    distance_samples: int = 5
    water_full_cm: float = 5.0
    water_empty_cm: float = 20.0
    tank_capacity_gallons: float = 5.0

    upper_camera_device: str = "/dev/video0"
    lower_camera_device: str = "/dev/video2"
    camera_resolution: str = "640x480"
    camera_skip_frames: int = 2
    fswebcam: str = "fswebcam"

    def __post_init__(self) -> None:
        checks = {
            "PORT must be 1-65535": 1 <= self.port <= 65535,
            f"LOG_LEVEL must be one of {sorted(_LOG_LEVELS)}": self.log_level.upper()
            in _LOG_LEVELS,
            "LIGHT_FREQUENCY must be positive": self.light_frequency > 0,
            "PUMP_FREQUENCY must be positive": self.pump_frequency > 0,
            "PUMP_DUTY must be 1-100": 1 <= self.pump_duty <= 100,
            "MAX_PUMP_RUN_SECONDS must be at least 1": self.max_pump_run_seconds >= 1,
            "SHUNT_OHMS must be positive": self.shunt_ohms > 0,
            "DISTANCE_SAMPLES must be at least 1": self.distance_samples >= 1,
            "CAMERA_SKIP_FRAMES must not be negative": self.camera_skip_frames >= 0,
        }
        failed = [message for message, ok in checks.items() if not ok]
        if failed:
            raise ValueError("; ".join(failed))

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> Settings:
        values: dict[str, Any] = {}
        for field in fields(cls):
            name = field.name.upper()
            raw = environ.get(name, "").strip()
            if not raw:
                continue
            try:
                values[field.name] = _PARSERS[str(field.type)](raw)
            except ValueError:
                raise ValueError(
                    f"{name}={raw!r} is not a valid {field.type}"
                ) from None
        return cls(**values)
