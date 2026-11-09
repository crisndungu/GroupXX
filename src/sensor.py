"""Simulated soil sensors for a 12-plant, four-zone site.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].

Each plant has a profile: species, zone, dry threshold, drying rate, and rainfall
and irrigation behaviour. Temperature follows a daily cycle, and evaporation
depends on temperature, so the moisture traces look like real soil rather than
a random walk.
"""
import json
import math
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class PlantProfile:
    device_id: str
    species: str
    zone: str
    dry_at: float          # percent moisture below which the plant needs water
    drain: float           # percent lost per simulated 10 minutes at 20 C
    rain_prob: float       # chance of a rainfall pulse on any step (outdoor zones)
    rain_mm: Tuple[float, float]
    irrigation: bool       # whether an automatic irrigation response is triggered


SITE: List[PlantProfile] = [
    PlantProfile("gn-01", "Tomato",     "Greenhouse North", 35, 0.55, 0.0, (0, 0), True),
    PlantProfile("gn-02", "Cucumber",   "Greenhouse North", 40, 0.60, 0.0, (0, 0), True),
    PlantProfile("gn-03", "Pepper",     "Greenhouse North", 35, 0.50, 0.0, (0, 0), True),
    PlantProfile("gs-01", "Basil",      "Greenhouse South", 40, 0.70, 0.0, (0, 0), True),
    PlantProfile("gs-02", "Lettuce",    "Greenhouse South", 45, 0.65, 0.0, (0, 0), False),
    PlantProfile("gs-03", "Strawberry", "Greenhouse South", 38, 0.60, 0.0, (0, 0), True),
    PlantProfile("hg-01", "Rosemary",   "Herb Garden",      20, 0.25, 0.03, (2, 6), False),
    PlantProfile("hg-02", "Thyme",      "Herb Garden",      20, 0.22, 0.03, (2, 6), False),
    PlantProfile("hg-03", "Mint",       "Herb Garden",      40, 0.45, 0.03, (2, 6), False),
    PlantProfile("cy-01", "Lavender",   "Courtyard",        18, 0.20, 0.04, (3, 9), False),
    PlantProfile("cy-02", "Fern",       "Courtyard",        45, 0.50, 0.04, (3, 9), False),
    PlantProfile("cy-03", "Olive",      "Courtyard",        15, 0.15, 0.04, (3, 9), False),
]

STEP_MINUTES = 10      # simulated minutes per reading
IRRIGATION_BOOST = 30  # percent added by an irrigation response


class SoilSensor:
    def __init__(self, profile: PlantProfile, seed: int = 0, start_hour: float = 6.0) -> None:
        self.profile = profile
        self.device_id = profile.device_id
        self.seq = 0
        self._rng = random.Random(seed)
        self._moisture = self._rng.uniform(profile.dry_at + 15, profile.dry_at + 40)
        self._sim_minutes = start_hour * 60.0  # simulated time of day

    def _temperature(self) -> float:
        hour = (self._sim_minutes / 60.0) % 24
        daily = 6.0 * math.sin(2 * math.pi * (hour - 9) / 24)  # peak mid-afternoon
        return 20.0 + daily + self._rng.uniform(-0.6, 0.6)

    def read(self) -> Tuple[int, bytes]:
        """Advance one simulated step and return (seq, payload bytes)."""

        p = self.profile
        self._sim_minutes += STEP_MINUTES
        temp = self._temperature()
        evaporation = p.drain * max(0.2, 0.5 + temp / 20.0) * self._rng.uniform(0.9, 1.1)
        self._moisture -= evaporation
        if p.rain_prob and self._rng.random() < p.rain_prob:
            self._moisture += self._rng.uniform(*p.rain_mm) * 0.5
        if p.irrigation and self._moisture < p.dry_at and self._rng.random() < 0.3:
            self._moisture += IRRIGATION_BOOST
        self._moisture = min(100.0, max(0.0, self._moisture))

        self.seq += 1
        reading: Dict[str, Any] = {
            "id": p.device_id,
            "species": p.species,
            "zone": p.zone,
            "dry_at": p.dry_at,
            "seq": self.seq,
            "ts": round(time.time(), 1),
            "moisture": round(self._moisture, 1),
            "temp_c": round(temp, 1),
        }
        return self.seq, json.dumps(reading, separators=(",", ":")).encode()


def build_sensors(count: int = 12, seed: int = 1) -> List[SoilSensor]:
    """Return sensors for the first `count` plants in SITE (max 12)."""
    count = max(1, min(count, len(SITE)))
    return [SoilSensor(profile, seed=seed + i) for i, profile in enumerate(SITE[:count])]