"""Command-line entry point: ``garden-api`` or ``python -m garden_api``."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .api import Api
from .config import Settings
from .garden import Garden
from .hardware.pump import force_pin_low
from .server import GardenServer

logger = logging.getLogger("garden_api")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="garden-api",
        description="Lean REST API for Gardyn hardware. Configured via environment variables.",
    )
    parser.add_argument(
        "--pump-off",
        action="store_true",
        help="drive the pump pin low and exit (systemd runs this after every stop or crash)",
    )
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"garden-api: invalid configuration: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s"
    )

    if args.pump_off:
        force_pin_low(settings.gpiomem, settings.pump_pin)
        return 0

    garden = Garden.from_settings(settings)
    server = GardenServer(
        (settings.host, settings.port), Api(garden, settings), settings.garden_api_key
    )
    signal.signal(signal.SIGTERM, _exit_on_signal)
    logger.info("listening on %s:%d", settings.host, settings.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        garden.shutdown()
    return 0


def _exit_on_signal(signum: int, _frame: object) -> None:
    raise SystemExit(0)


if __name__ == "__main__":
    sys.exit(main())
