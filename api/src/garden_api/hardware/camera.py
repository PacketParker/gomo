"""USB camera stills via fswebcam, captured on request and returned as JPEG bytes."""

from __future__ import annotations

import subprocess
import threading

from ..errors import HardwareUnavailable

_JPEG_MAGIC = b"\xff\xd8"
_TIMEOUT_SECONDS = 30


class Camera:
    def __init__(
        self,
        device: str,
        resolution: str,
        skip_frames: int,
        executable: str = "fswebcam",
    ) -> None:
        self._command = [
            executable, "-q", "-d", device, "--no-banner", "-r", resolution,
            "-S", str(skip_frames), "--jpeg", "85", "-",  # "-" writes to stdout
        ]  # fmt: skip
        self._lock = threading.Lock()  # one capture per device at a time

    def capture(self) -> bytes:
        with self._lock:
            try:
                result = subprocess.run(
                    self._command, capture_output=True, timeout=_TIMEOUT_SECONDS
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HardwareUnavailable(f"camera capture failed: {exc}") from exc
        if result.returncode != 0 or not result.stdout.startswith(_JPEG_MAGIC):
            detail = (
                result.stderr.decode(errors="replace").strip() or "no image produced"
            )
            raise HardwareUnavailable(f"camera capture failed: {detail}")
        return result.stdout
