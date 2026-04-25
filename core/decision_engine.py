from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from ai import ThreatAnalysis
from models import Asset, ResourceState, Threat, ThreatType


class DecisionAction(str, Enum):
    ENGAGE_AIR_DEFENSE = "engage_air_defense"
    SCRAMBLE_FIGHTER = "scramble_fighter"
    DEPLOY_DRONE = "deploy_drone"
    HOLD = "hold"


@dataclass
class Decision:
    threat_id: int
    action: DecisionAction
    launch_from: str
    priority_score: float
    rationale: str


class DecisionEngine:
    """Deterministic rule-based planner for all final actions."""

    def __init__(self, min_air_defense_reserve: int = 2, min_fighter_reserve: int = 1):
        self.min_air_defense_reserve = min_air_defense_reserve
        self.min_fighter_reserve = min_fighter_reserve

    def decide(
        self,
        threats: Iterable[Threat],
        analyses: dict[int, ThreatAnalysis],
        resources: ResourceState,
        assets: Iterable[Asset],
    ) -> list[Decision]:

        alive_assets = [asset for asset in assets if asset.is_alive()]
        if not alive_assets:
            return []

        candidates = [t for t in threats if t.alive and not t.assigned]
        if not candidates:
            return []

        asset_lookup = {asset.asset_id: asset for asset in alive_assets}

        # --- SCORE THREATS ---
        scored_threats: list[tuple[float, Threat, ThreatAnalysis]] = []

        for threat in candidates:
            analysis = analyses.get(threat.threat_id)
            if not analysis:
                continue

            likely_asset = asset_lookup.get(analysis.likely_target)
            if not likely_asset:
                likely_asset = min(
                    alive_assets,
                    key=lambda a: threat.distance_to(a.x, a.y)
                )

            proximity = 1.0 - min(
                1.0,
                threat.distance_to(likely_asset.x, likely_asset.y) / 900.0
            )

            score = (
                0.40 * analysis.threat_level
                + 0.30 * analysis.urgency
                + 0.20 * analysis.confidence
                + 0.10 * proximity
            )

            scored_threats.append((score, threat, analysis))

        scored_threats.sort(key=lambda x: x[0], reverse=True)

        # --- RESOURCE SNAPSHOT ---
        planned_ammo = resources.air_defense_ammo
        planned_fighters = resources.fighters_available  # ✅ NEW
        planned_drones = resources.drones_ready

        air_defense_ready = resources.air_defense_cooldown <= 0.0
        fighter_ready = resources.fighter_launch_cooldown <= 0.0
        drone_ready = resources.drone_launch_cooldown <= 0.0

        missile_count = sum(1 for t in candidates if t.threat_type == ThreatType.MISSILE)
        future_pressure = min(1.0, len(candidates) / 5.0 + 0.35 * missile_count / 4.0)

        decisions: list[Decision] = []

        # --- MAIN LOOP ---
        for score, threat, analysis in scored_threats:

            high_priority = (
                score >= 0.68
                or analysis.urgency >= 0.78
                or analysis.threat_level >= 0.80
            )

            conservation_mode = (
                future_pressure >= 0.65
                or planned_ammo <= self.min_air_defense_reserve
                or planned_fighters <= self.min_fighter_reserve
            )

            # =========================
            # AIR DEFENSE (MISSILES)
            # =========================
            if (
                threat.threat_type == ThreatType.MISSILE
                and air_defense_ready
                and planned_ammo > 0
            ):
                if planned_ammo > self.min_air_defense_reserve or high_priority:
                    launch_from = self._nearest_source(
                        threat, alive_assets, ("air_defense",)
                    )

                    decisions.append(
                        Decision(
                            threat_id=threat.threat_id,
                            action=DecisionAction.ENGAGE_AIR_DEFENSE,
                            launch_from=launch_from,
                            priority_score=score,
                            rationale="Missile threat engaged using air defense.",
                        )
                    )

                    planned_ammo -= 1
                    air_defense_ready = False
                    continue

            # =========================
            # FIGHTERS (REUSABLE)
            # =========================
            if fighter_ready and planned_fighters > 0:

                if high_priority or (score >= 0.58 and not conservation_mode):

                    launch_from = self._nearest_source(
                        threat, alive_assets, ("fighter_base",)
                    )

                    decisions.append(
                        Decision(
                            threat_id=threat.threat_id,
                            action=DecisionAction.SCRAMBLE_FIGHTER,
                            launch_from=launch_from,
                            priority_score=score,
                            rationale="Fighter deployed (reusable asset with cooldown).",
                        )
                    )

                    # ❗ IMPORTANT: do NOT consume fighter permanently
                    planned_fighters -= 1   # temporary planning only
                    fighter_ready = False
                    continue

            # =========================
            # DRONES
            # =========================
            if (
                threat.threat_type == ThreatType.DRONE
                and drone_ready
                and planned_drones > 0
                and not conservation_mode
                and score >= 0.45
            ):

                launch_from = self._nearest_source(
                    threat, alive_assets, ("drone_hub", "base")
                )

                decisions.append(
                    Decision(
                        threat_id=threat.threat_id,
                        action=DecisionAction.DEPLOY_DRONE,
                        launch_from=launch_from,
                        priority_score=score,
                        rationale="Drone used for low-cost interception.",
                    )
                )

                planned_drones -= 1
                drone_ready = False
                continue

            # =========================
            # HOLD
            # =========================
            if threat.threat_type == ThreatType.DRONE and conservation_mode:
                rationale = "Holding to preserve resources for higher threats."
            else:
                rationale = "No efficient resource available."

            decisions.append(
                Decision(
                    threat_id=threat.threat_id,
                    action=DecisionAction.HOLD,
                    launch_from="none",
                    priority_score=score,
                    rationale=rationale,
                )
            )

        return decisions

    def _nearest_source(self, threat: Threat, assets: list[Asset], kinds: tuple[str, ...]) -> str:
        candidates = [a for a in assets if a.kind in kinds]
        if not candidates:
            return "unknown"

        return min(
            candidates,
            key=lambda a: threat.distance_to(a.x, a.y)
        ).asset_id