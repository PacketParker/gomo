"""Water tank geometry: sensor distance -> gallons remaining."""

from __future__ import annotations


def gallons_remaining(
    distance_cm: float, full_cm: float, empty_cm: float, capacity_gallons: float
) -> float | None:
    """Linear estimate between the "full" and "empty" sensor distances.

    The sensor looks down at the water, so a larger distance means less water.
    Returns None when the calibration can't produce a meaningful answer.
    """
    span = empty_cm - full_cm
    if span <= 0 or capacity_gallons <= 0:
        return None
    fraction = min(1.0, max(0.0, (empty_cm - distance_cm) / span))
    return round(fraction * capacity_gallons, 1)
