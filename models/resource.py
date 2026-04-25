from dataclasses import dataclass, field


@dataclass
class ResourceState:
    air_defense_ammo: int = 14
    fighters_ready: int = 3
    drones_ready: int = 2

    max_fighters: int = 3
    max_drones: int = 2

    air_defense_cooldown: float = 0.0
    fighter_launch_cooldown: float = 0.0
    drone_launch_cooldown: float = 0.0

    _fighter_recovery: list[float] = field(default_factory=list)
    _drone_recovery: list[float] = field(default_factory=list)

    def tick(self, dt: float) -> None:
        self.air_defense_cooldown = max(0.0, self.air_defense_cooldown - dt)
        self.fighter_launch_cooldown = max(0.0, self.fighter_launch_cooldown - dt)
        self.drone_launch_cooldown = max(0.0, self.drone_launch_cooldown - dt)

        self._update_recovery(self._fighter_recovery, dt, "fighters_ready", self.max_fighters)
        self._update_recovery(self._drone_recovery, dt, "drones_ready", self.max_drones)

    def can_fire_air_defense(self) -> bool:
        return self.air_defense_ammo > 0 and self.air_defense_cooldown <= 0.0

    def can_launch_fighter(self) -> bool:
        return self.fighters_ready > 0 and self.fighter_launch_cooldown <= 0.0

    def can_launch_drone(self) -> bool:
        return self.drones_ready > 0 and self.drone_launch_cooldown <= 0.0

    def consume_air_defense(self) -> bool:
        if not self.can_fire_air_defense():
            return False

        self.air_defense_ammo -= 1
        self.air_defense_cooldown = 0.8
        return True

    def launch_fighter(self) -> bool:
        if not self.can_launch_fighter():
            return False

        self.fighters_ready -= 1
        self.fighter_launch_cooldown = 1.6
        self._fighter_recovery.append(9.0)
        return True

    def launch_drone(self) -> bool:
        if not self.can_launch_drone():
            return False

        self.drones_ready -= 1
        self.drone_launch_cooldown = 1.2
        self._drone_recovery.append(6.5)
        return True

    def _update_recovery(self, timers: list[float], dt: float, attr: str, max_value: int) -> None:
        recovered = 0
        next_timers: list[float] = []

        for timer in timers:
            timer -= dt
            if timer <= 0:
                recovered += 1
            else:
                next_timers.append(timer)

        setattr(self, attr, min(max_value, getattr(self, attr) + recovered))
        timers[:] = next_timers
