"""INA219 current/voltage monitor on the pump supply, read over Linux i2c-dev."""

from __future__ import annotations

import fcntl
import os
import threading
from dataclasses import dataclass

from ..errors import HardwareUnavailable

_I2C_SLAVE = 0x0703  # ioctl: set the target address for read()/write()

_REG_CONFIG = 0x00
_REG_SHUNT_VOLTAGE = 0x01
_REG_BUS_VOLTAGE = 0x02

# 32 V bus range, +/-320 mV shunt range, continuous conversion, and 128-sample
# averaging (68 ms) on both ADCs. The pump PWM runs at 50 Hz. A single 0.5 ms
# sample usually falls between pulses and reads ~0. Averaging over several
# 20 ms cycles gives the mean current.
_BUS_RANGE_32V = 1 << 13
_SHUNT_RANGE_320MV = 0b11 << 11
_BUS_ADC_128_SAMPLES = 0b1111 << 7
_SHUNT_ADC_128_SAMPLES = 0b1111 << 3
_MODE_CONTINUOUS = 0b111
_CONFIG = (
    _BUS_RANGE_32V
    | _SHUNT_RANGE_320MV
    | _BUS_ADC_128_SAMPLES
    | _SHUNT_ADC_128_SAMPLES
    | _MODE_CONTINUOUS
)
_SHUNT_LSB_MV = 0.01
_BUS_LSB_V = 0.004


@dataclass(frozen=True)
class PowerReading:
    bus_voltage_v: float
    shunt_voltage_mv: float
    current_ma: float
    power_mw: float


def decode(shunt_raw: int, bus_raw: int, shunt_ohms: float) -> PowerReading:
    """Convert raw register values (shunt signed, bus unsigned) to units."""
    shunt_mv = shunt_raw * _SHUNT_LSB_MV
    bus_v = (bus_raw >> 3) * _BUS_LSB_V  # low 3 bits are status flags
    current_ma = shunt_mv / shunt_ohms
    return PowerReading(
        bus_voltage_v=round(bus_v, 3),
        shunt_voltage_mv=round(shunt_mv, 3),
        current_ma=round(current_ma, 1),
        power_mw=round(bus_v * current_ma, 1),
    )


class Ina219:
    def __init__(self, bus: str, address: int, shunt_ohms: float) -> None:
        self._shunt_ohms = shunt_ohms
        self._lock = threading.Lock()
        self._fd = os.open(bus, os.O_RDWR)
        try:
            fcntl.ioctl(self._fd, _I2C_SLAVE, address)
            os.write(self._fd, bytes([_REG_CONFIG, *_CONFIG.to_bytes(2, "big")]))
        except OSError:
            os.close(self._fd)
            raise

    def read(self) -> PowerReading:
        try:
            shunt = self._read_register(_REG_SHUNT_VOLTAGE, signed=True)
            bus = self._read_register(_REG_BUS_VOLTAGE, signed=False)
        except OSError as exc:
            raise HardwareUnavailable(f"INA219 read failed: {exc}") from exc
        return decode(shunt, bus, self._shunt_ohms)

    def close(self) -> None:
        os.close(self._fd)

    def _read_register(self, register: int, *, signed: bool) -> int:
        with self._lock:  # pointer write + read must not interleave
            os.write(self._fd, bytes([register]))
            return int.from_bytes(os.read(self._fd, 2), "big", signed=signed)
