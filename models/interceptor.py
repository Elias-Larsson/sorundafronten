from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class InterceptorType(str, Enum):
    AIR_DEFENSE = "air_defense"
    FIGHTER = "fighter"
    DRONE = "drone"


@dataclass
class Interceptor:
    interceptor_id: int
    interceptor_type: InterceptorType
    source_id: str
    target_threat_id: int
    x: float
    y: float
    speed: float
    alive: bool = True

    def update_toward(self, target_x: float, target_y: float, dt: float) -> bool:
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.hypot(dx, dy)

        if distance <= 1e-6:
            return True

        step = self.speed * dt
        if step >= distance:
            self.x = target_x
            self.y = target_y
            return True

        self.x += dx / distance * step
        self.y += dy / distance * step
        return False
