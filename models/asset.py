from dataclasses import dataclass


@dataclass
class Asset:
    asset_id: str
    kind: str
    x: float
    y: float
    hp: int
    max_hp: int
    strategic_value: float

    def is_alive(self) -> bool:
        return self.hp > 0
