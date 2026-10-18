"""GPIO register access for BCM2835/2837/2711 (Raspberry Pi Zero through Pi 4).

``/dev/gpiomem`` exposes just the GPIO register block to members of the
``gpio`` group, so no root, daemon, or third-party library is needed.
"""

from __future__ import annotations

import mmap
import os
import threading

_MAP_SIZE = 4096
_PIN_COUNT = 54

# 32-bit register offsets, as word indexes.
_FSEL = 0x00 // 4  # function select: 3 bits per pin, 10 pins per register
_SET = 0x1C // 4
_CLR = 0x28 // 4
_LEV = 0x34 // 4

_INPUT = 0b000
_OUTPUT = 0b001


class Gpio:
    """Memory-mapped GPIO. Pins use BCM numbering."""

    def __init__(self, path: str = "/dev/gpiomem") -> None:
        fd = os.open(path, os.O_RDWR | os.O_SYNC)
        try:
            self._map = mmap.mmap(fd, _MAP_SIZE)
        finally:
            os.close(fd)
        self._registers = memoryview(self._map).cast("I")
        self._fsel_lock = threading.Lock()

    def set_output(self, pin: int) -> None:
        self._set_function(pin, _OUTPUT)

    def set_input(self, pin: int) -> None:
        self._set_function(pin, _INPUT)

    def write(self, pin: int, high: bool) -> None:
        _check_pin(pin)
        bank, bit = divmod(pin, 32)
        self._registers[(_SET if high else _CLR) + bank] = 1 << bit

    def read(self, pin: int) -> bool:
        _check_pin(pin)
        bank, bit = divmod(pin, 32)
        return bool(self._registers[_LEV + bank] >> bit & 1)

    def close(self) -> None:
        self._registers.release()
        self._map.close()

    def _set_function(self, pin: int, function: int) -> None:
        _check_pin(pin)
        register, slot = divmod(pin, 10)
        shift = slot * 3
        with self._fsel_lock:  # read-modify-write shared with 9 other pins
            value = self._registers[_FSEL + register]
            self._registers[_FSEL + register] = (
                value & ~(0b111 << shift) | function << shift
            )


def _check_pin(pin: int) -> None:
    if not 0 <= pin < _PIN_COUNT:
        raise ValueError(f"GPIO pin {pin} is out of range 0-{_PIN_COUNT - 1}")
