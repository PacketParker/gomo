"""Routes, input validation, and response shapes.

Independent of the transport: takes a method, a normalized path and a raw body,
and returns a Response. Light, sensor and camera paths are compatible with the
garden-of-eden REST API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from .config import Settings
from .errors import HardwareUnavailable
from .garden import Garden
from .tank import gallons_remaining

logger = logging.getLogger(__name__)

Json = dict[str, Any]
T = TypeVar("T")


class BadRequest(ValueError):
    """The request is malformed or a value is out of range (HTTP 400)."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    content_type: str = "application/json"

    @classmethod
    def json(cls, payload: Json, status: int = 200) -> Response:
        return cls(status, json.dumps(payload).encode())

    @classmethod
    def error(cls, status: int, message: str) -> Response:
        return cls.json({"error": message}, status)


class Api:
    def __init__(self, garden: Garden, settings: Settings) -> None:
        self._garden = garden
        self._settings = settings
        self._routes: dict[tuple[str, str], Callable[[Json], Response]] = {
            ("GET", "/light/brightness"): self.get_light,
            ("POST", "/light/brightness"): self.set_light,
            ("POST", "/light/on"): lambda _: self._light(100),
            ("POST", "/light/off"): lambda _: self._light(0),
            ("GET", "/pump"): self.get_pump,
            ("POST", "/pump/on"): self.pump_on,
            ("POST", "/pump/off"): self.pump_off,
            ("GET", "/pump/stats"): self.get_power,
            ("GET", "/distance"): self.get_water,
            ("GET", "/distance/measure"): self.get_water,
            ("GET", "/camera/upper"): lambda _: self._capture("upper"),
            ("GET", "/camera/lower"): lambda _: self._capture("lower"),
        }
        self._paths = {path for _, path in self._routes}

    def handle(self, method: str, path: str, body: bytes) -> Response:
        handler = self._routes.get((method, path))
        if handler is None:
            if path in self._paths:
                return Response.error(405, "method not allowed")
            return Response.error(404, "not found")
        try:
            return handler(_parse_body(body))
        except BadRequest as exc:
            return Response.error(400, str(exc))
        except HardwareUnavailable as exc:
            return Response.error(503, str(exc))
        except Exception:
            logger.exception("unhandled error on %s %s", method, path)
            return Response.error(500, "internal error")  # details stay in the log

    # -- light

    def get_light(self, _: Json) -> Response:
        return Response.json({"value": _require(self._garden.light, "light").level})

    def set_light(self, body: Json) -> Response:
        return self._light(_level(body))

    def _light(self, level: float) -> Response:
        return Response.json(
            {"value": _require(self._garden.light, "light").set_level(level)}
        )

    # -- pump

    def get_pump(self, _: Json) -> Response:
        pump = _require(self._garden.pump, "pump")
        return Response.json({"on": pump.is_on, "seconds_left": pump.seconds_left})

    def pump_on(self, body: Json) -> Response:
        """Optional {"seconds": N} sets the run time. The default and the limit
        are MAX_PUMP_RUN_SECONDS. The pump stops automatically."""
        limit = self._settings.max_pump_run_seconds
        seconds = _integer(body, "seconds", 1, limit) if "seconds" in body else None
        ran = _require(self._garden.pump, "pump").on(seconds)
        return Response.json({"on": True, "seconds": ran})

    def pump_off(self, _: Json) -> Response:
        _require(self._garden.pump, "pump").off()
        return Response.json({"on": False})

    # -- sensors

    def get_power(self, _: Json) -> Response:
        reading = _require(self._garden.power, "power monitor").read()
        return Response.json(
            {
                "BusVoltage": reading.bus_voltage_v,
                "BusCurrent": reading.current_ma,
                "Power": reading.power_mw,
                "ShuntVoltage": reading.shunt_voltage_mv,
            }
        )

    def get_water(self, _: Json) -> Response:
        s = self._settings
        distance = _require(self._garden.water, "water-level sensor").measure_cm()
        gallons = gallons_remaining(
            distance, s.water_full_cm, s.water_empty_cm, s.tank_capacity_gallons
        )
        return Response.json({"distance": distance, "gallons": gallons})

    def _capture(self, name: str) -> Response:
        camera = _require(self._garden.cameras.get(name), f"{name} camera")
        return Response(200, camera.capture(), "image/jpeg")


def _require(device: T | None, name: str) -> T:
    if device is None:
        raise HardwareUnavailable(f"{name} unavailable")
    return device


def _parse_body(body: bytes) -> Json:
    if not body:
        return {}
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise BadRequest("body is not valid JSON") from None
    if not isinstance(data, dict):
        raise BadRequest("body must be a JSON object")
    return data


def _level(body: Json) -> float:
    value = body.get("value")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 100
    ):
        raise BadRequest("'value' must be a number between 0 and 100")
    return value


def _integer(body: Json, key: str, low: int, high: int) -> int:
    value = body.get(key)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not low <= value <= high
    ):
        raise BadRequest(f"'{key}' must be an integer between {low} and {high}")
    return value
