from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceState:
    # -----------------------------
    # STOCKS
    # -----------------------------
    air_defense_ammo: int = 20
    air_defense_max: int = 20  # ✅ NEW (optional cap)

    fuel_total: int = 10
    fighter_fuel_reserved: int = 0

    fighters_total: int = 2
    fighters_busy: float = 0.0

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
    fighter_return_rate: float = 0.25
    fighter_launch_delay: float = 1.5

    air_defense_delay: float = 1.0
    drone_launch_delay: float = 2.0

    # ✅ NEW: resupply config
    air_defense_resupply_per_turn: int = 2

    # -----------------------------
    # DERIVED
    # -----------------------------
    @property
    def fighters_available(self) -> int:
        return max(0, int(self.fighters_total - self.fighters_busy))

    @property
    def fuel_available(self) -> int:
        return max(0, int(self.fuel_total - self.fighter_fuel_reserved))

    # -----------------------------
    # ACTIONS
    # -----------------------------
    def consume_air_defense(self) -> bool:
        if self.air_defense_ammo <= 0 or self.air_defense_cooldown > 0:
            return False

        self.air_defense_ammo -= 1
        self.air_defense_cooldown = self.air_defense_delay
        return True

    def launch_fighter(self) -> bool:
        if self.fighters_available <= 0 or self.fighter_launch_cooldown > 0:
            return False

        if self.fuel_available <= 0:
            return False

        self.fighters_busy += 1
        self.fighter_launch_cooldown = self.fighter_launch_delay
        self.fighter_fuel_reserved += 1
        return True

    def recover_fighter(self) -> None:
        self.fighters_busy = max(0.0, self.fighters_busy - 1.0)

    def fighter_returned(self) -> None:
        if self.fighter_fuel_reserved > 0:
            self.fighter_fuel_reserved -= 1
        self.fuel_total = max(0, self.fuel_total - 1)

    def cancel_fighter_fuel_reservation(self) -> None:
        if self.fighter_fuel_reserved > 0:
            self.fighter_fuel_reserved -= 1

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

        # Fighter return over time
        if self.fighters_busy > 0:
            self.fighters_busy -= self.fighter_return_rate * dt
            if self.fighters_busy < 0:
                self.fighters_busy = 0