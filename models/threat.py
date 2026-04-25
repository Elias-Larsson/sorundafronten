from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class ThreatType(str, Enum):
    MISSILE = "missile"
    DRONE = "drone"


@dataclass
class Threat:
    threat_id: int
    threat_type: ThreatType
    x: float
    y: float
    vx: float
    vy: float
    intended_target_id: str
    assigned: bool = False
    alive: bool = True

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self.x - x, self.y - y)

    def eta_seconds(self, x: float, y: float) -> float:
        if self.speed <= 0:
            return float("inf")
        return self.distance_to(x, y) / self.speed
