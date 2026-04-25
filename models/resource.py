from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceState:
    # -----------------------------
    # STOCKS
    # -----------------------------
    air_defense_ammo: int = 6

    fighters_total: int = 2
    fighters_busy: float = 0.0  # float for smooth return over time

    drones_ready: int = 3

    # -----------------------------
    # COOLDOWNS (seconds)
    # -----------------------------
    air_defense_cooldown: float = 0.0
    fighter_launch_cooldown: float = 0.0
    drone_launch_cooldown: float = 0.0

    # -----------------------------
    # CONFIG
    # -----------------------------
    fighter_return_rate: float = 0.25   # fighters per second
    fighter_launch_delay: float = 1.5

    air_defense_delay: float = 1.0
    air_defense_radius: float = 100.0
    drone_launch_delay: float = 2.0

    # -----------------------------
    # DERIVED
    # -----------------------------
    @property
    def fighters_available(self) -> int:
        return max(0, int(self.fighters_total - self.fighters_busy))
    

    def in_air_defense_range(self, source_x: float, source_y: float,
                        target_x: float, target_y: float) -> bool:
        dx = target_x - source_x
        dy = target_y - source_y
        distance = (dx * dx + dy * dy) ** 0.5
        return distance <= self.air_defense_radius

    # -----------------------------
    # ACTIONS
    # -----------------------------
    def consume_air_defense(self,
                        source_x: float,
                        source_y: float,
                        target_x: float,
                        target_y: float) -> bool:

        if self.air_defense_ammo <= 0 or self.air_defense_cooldown > 0:
            return False

        if not self.in_air_defense_range(source_x, source_y, target_x, target_y):
            return False

        self.air_defense_ammo -= 1
        self.air_defense_cooldown = self.air_defense_delay
        return True

    def launch_fighter(self) -> bool:
        if self.fighters_available <= 0 or self.fighter_launch_cooldown > 0:
            return False

        self.fighters_busy += 1
        self.fighter_launch_cooldown = self.fighter_launch_delay
        return True

    def launch_drone(self) -> bool:
        if self.drones_ready <= 0 or self.drone_launch_cooldown > 0:
            return False

        self.drones_ready -= 1
        self.drone_launch_cooldown = self.drone_launch_delay
        return True

    # -----------------------------
    # UPDATE LOOP
    # -----------------------------
    def tick(self, dt: float) -> None:
        # Cooldowns
        if self.air_defense_cooldown > 0:
            self.air_defense_cooldown -= dt
            if self.air_defense_cooldown < 0:
                self.air_defense_cooldown = 0

        if self.fighter_launch_cooldown > 0:
            self.fighter_launch_cooldown -= dt
            if self.fighter_launch_cooldown < 0:
                self.fighter_launch_cooldown = 0

        if self.drone_launch_cooldown > 0:
            self.drone_launch_cooldown -= dt
            if self.drone_launch_cooldown < 0:
                self.drone_launch_cooldown = 0

        # Fighter return over time
        if self.fighters_busy > 0:
            self.fighters_busy -= self.fighter_return_rate * dt

            if self.fighters_busy < 0:
                self.fighters_busy = 0