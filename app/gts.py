"""Minimal GTS named-interval → Ma bounds (common stages / epochs)."""

from __future__ import annotations

# Approximate ICS chart ages (Ma). Good enough for MVP normalization.
GTS_INTERVALS: dict[str, tuple[float, float]] = {
    # Quaternary
    "holocene": (0.0117, 0.0),
    "pleistocene": (2.58, 0.0117),
    "quaternary": (2.58, 0.0),
    # Neogene
    "pliocene": (5.333, 2.58),
    "miocene": (23.03, 5.333),
    "neogene": (23.03, 2.58),
    # Paleogene
    "oligocene": (33.9, 23.03),
    "eocene": (56.0, 33.9),
    "paleocene": (66.0, 56.0),
    "paleogene": (66.0, 23.03),
    # Cretaceous stages (subset)
    "maastrichtian": (72.1, 66.0),
    "campanian": (83.6, 72.1),
    "santonian": (86.3, 83.6),
    "coniacian": (89.8, 86.3),
    "turonian": (93.9, 89.8),
    "cenomanian": (100.5, 93.9),
    "late cretaceous": (100.5, 66.0),
    "early cretaceous": (145.0, 100.5),
    "cretaceous": (145.0, 66.0),
    # Jurassic / Triassic coarse
    "jurassic": (201.3, 145.0),
    "triassic": (251.9, 201.3),
    "permian": (298.9, 251.9),
    "carboniferous": (358.9, 298.9),
    "devonian": (419.2, 358.9),
    "silurian": (443.8, 419.2),
    "ordovician": (485.4, 443.8),
    "cambrian": (538.8, 485.4),
}


def resolve_interval(name: str | None) -> dict[str, float | str] | None:
    if not name:
        return None
    key = name.strip().lower()
    if key not in GTS_INTERVALS:
        return None
    age_max_ma, age_min_ma = GTS_INTERVALS[key]  # older, younger
    return {
        "interval": name.strip(),
        "age_max_ma": age_max_ma,
        "age_min_ma": age_min_ma,
    }


def normalize_age_bounds(
    age_min: float | None,
    age_max: float | None,
    interval_hint: str | None = None,
) -> dict[str, float | str | None]:
    """
    Return age_min_ma (younger) and age_max_ma (older).
    Named interval fills gaps when numeric bounds are missing.
    """
    resolved = resolve_interval(interval_hint)
    younger = age_min
    older = age_max
    epoch = None
    stage = None
    if resolved:
        stage = str(resolved["interval"])
        if younger is None:
            younger = float(resolved["age_min_ma"])
        if older is None:
            older = float(resolved["age_max_ma"])
    # Swap if caller passed inverted bounds
    if younger is not None and older is not None and younger > older:
        younger, older = older, younger
    return {
        "epoch": epoch,
        "stage": stage,
        "age_min_ma": younger,
        "age_max_ma": older,
    }
