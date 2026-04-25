from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceState:
    # -----------------------------
    # STOCKS
    # -----------------------------
    air_defense_ammo: int = 20
    air_defense_max: int = 20  # ✅ NEW (optional cap)

    fuel: int = 10
    fuel_max: int = 10
    fuel_resupply_per_turn: int = 2

    fighters_total: int = 3
    fighters_busy: float = 0.0  # number of fighters currently committed

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
    fighter_launch_delay: float = 0.0

    air_defense_delay: float = 1.0
    air_defense_radius: float = 100000.0
    drone_launch_delay: float = 2.0

    # ✅ NEW: resupply config
    air_defense_resupply_per_turn: int = 2

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

    def add_fuel(self, amount: int) -> None:
        if amount <= 0:
            return
        self.fuel = min(self.fuel_max, self.fuel + amount)

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

        if self.fuel <= 0:
            return False

        self.fighters_busy += 1
        self.fighter_launch_cooldown = self.fighter_launch_delay
        self.fuel = max(0, self.fuel - 1)
        return True

    def recover_fighter(self) -> None:
        self.fighters_busy = max(0.0, self.fighters_busy - 1.0)

    def launch_drone(self) -> bool:
        if self.drones_ready <= 0 or self.drone_launch_cooldown > 0:
            return False

        self.drones_ready -= 1
        self.drone_launch_cooldown = self.drone_launch_delay
        return True

    # -----------------------------
    # 🆕 TURN-BASED RESUPPLY
    # -----------------------------
    def resupply_after_turn(self) -> None:
        self.air_defense_ammo += self.air_defense_resupply_per_turn

        # Optional cap
        if self.air_defense_ammo > self.air_defense_max:
            self.air_defense_ammo = self.air_defense_max

        self.add_fuel(self.fuel_resupply_per_turn)

    # -----------------------------
    # UPDATE LOOP (REAL-TIME)
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

        # fighters_busy is recovered explicitly when fighter returns
