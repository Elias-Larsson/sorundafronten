from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import json
import random
from pathlib import Path
import threading
from typing import Deque

from ai import ThreatAnalysis, ThreatAnalyzer
from core.decision_engine import Decision, DecisionAction, DecisionEngine
from core.map_loader import MapData, MapProjector, load_map_data
from models import Asset, Interceptor, InterceptorType, ResourceState, Threat, ThreatType


class TurnPhase(str, Enum):
    PLAYER_PLANNING = "player_planning"
    AI_THINKING = "ai_thinking"
    RESOLVING = "resolving"


@dataclass(frozen=True)
class PlannedThreat:
    threat_type: ThreatType
    target_asset_id: str


class Simulation:
    def __init__(
        self,
        width: int,
        height: int,
        seed: int = 7,
        map_data: MapData | None = None,
        projector: MapProjector | None = None,
    ):
        self.width = width
        self.height = height

        self.rng = random.Random(seed)

        self.map_data = map_data
        if self.map_data is None:
            root = Path(__file__).resolve().parent.parent
            csv_path = root / "map.csv"
            svg_path = root / "map.svg"
            if csv_path.exists() and svg_path.exists():
                self.map_data = load_map_data(csv_path, svg_path)

        if projector is None:
            if self.map_data is not None:
                self.projector = MapProjector(
                    self.map_data.world_width_km,
                    self.map_data.world_height_km,
                    width,
                    height,
                )
            else:
                self.projector = MapProjector(1666.7, 1300.0, width, height)
        else:
            self.projector = projector

        self.assets = self._build_assets()
        self.enemy_launch_points = self._build_enemy_launch_points()
        self.resources = ResourceState()

        self.analyzer = ThreatAnalyzer()
        self.ai_provider_status = self.analyzer.provider_status
        self.decision_engine = DecisionEngine()

        self.phase = TurnPhase.PLAYER_PLANNING
        self.turn_number = 1

        self.pending_turn_spawns: list[PlannedThreat] = []
        self.turn_analyses: dict[int, ThreatAnalysis] = {}
        self.selected_target_id = ""

        self._ai_thread: threading.Thread | None = None
        self._ai_result: dict[int, ThreatAnalysis] | None = None
        self._ai_error: str | None = None
        self._ai_result_lock = threading.Lock()

        self.threats: list[Threat] = []
        self.interceptors: list[Interceptor] = []

        self.time_elapsed = 0.0

        self.next_threat_id = 1
        self.next_interceptor_id = 1

        self.latest_ai_json: list[str] = []
        self.latest_decisions: list[Decision] = []
        self.event_log: Deque[str] = deque(maxlen=12)

        self.neutralized_count = 0
        self.impact_count = 0

        self._sync_selected_target()

    def update(self, dt: float) -> None:
        if self.phase == TurnPhase.PLAYER_PLANNING:
            self._sync_selected_target()
            return

        if self.phase == TurnPhase.AI_THINKING:
            self._poll_ai_result()
            return

        self.time_elapsed += dt
        self.resources.tick(dt)

        self._update_threats(dt)

        analyses = self.turn_analyses
        self.latest_decisions = self.decision_engine.decide(
            threats=self.threats,
            analyses=analyses,
            resources=self.resources,
            assets=self.assets,
        )

        self._execute_decisions(self.latest_decisions)
        self._update_interceptors(dt)
        self._purge_destroyed_objects()

        if not self.threats and not self.interceptors:
            completed_turn = self.turn_number
            self.phase = TurnPhase.PLAYER_PLANNING
            self.turn_number += 1
            self.turn_analyses = {}
            self.latest_decisions = []
            self._sync_selected_target()
            self.resources.add_fuel(self.resources.fuel_resupply_per_turn)
            self._log(f"Turn {completed_turn} resolved. Queue threats for turn {self.turn_number}.")

    def spawn_manual(self, threat_type: ThreatType) -> None:
        self.queue_threat(threat_type)

    def queue_threat(self, threat_type: ThreatType, target_asset_id: str | None = None) -> bool:
        if self.phase != TurnPhase.PLAYER_PLANNING or self.is_mission_lost():
            return False

        self._sync_selected_target()
        selected_target = target_asset_id or self.selected_target_id
        if not self._is_targetable_asset_id(selected_target):
            return False

        self.pending_turn_spawns.append(PlannedThreat(threat_type=threat_type, target_asset_id=selected_target))
        return True

    def clear_planned_threats(self) -> bool:
        if self.phase != TurnPhase.PLAYER_PLANNING:
            return False

        self.pending_turn_spawns.clear()
        return True

    def start_turn(self) -> bool:
        if self.phase != TurnPhase.PLAYER_PLANNING or self.is_mission_lost():
            return False

        if not self.pending_turn_spawns:
            self._log("No threats queued. Add threats before starting the turn.")
            return False

        self.latest_decisions = []
        self.latest_ai_json = []

        queued_count = len(self.pending_turn_spawns)
        for planned in self.pending_turn_spawns:
            self._spawn_threat(planned.threat_type, planned.target_asset_id)

        self.pending_turn_spawns.clear()
        self.phase = TurnPhase.AI_THINKING
        self.ai_provider_status = f"{self.analyzer.backend}:waiting-response"
        self._log(f"Turn {self.turn_number} submitted with {queued_count} threats. Waiting for AI analysis.")

        self._start_ai_worker()
        return True

    def is_player_turn(self) -> bool:
        return self.phase == TurnPhase.PLAYER_PLANNING

    def phase_label(self) -> str:
        labels = {
            TurnPhase.PLAYER_PLANNING: "PLAYER PLANNING",
            TurnPhase.AI_THINKING: "WAITING FOR GEMINI",
            TurnPhase.RESOLVING: "SIMULATION RESOLVING",
        }
        return labels[self.phase]

    def queued_counts(self) -> tuple[int, int]:
        missiles = sum(1 for planned in self.pending_turn_spawns if planned.threat_type == ThreatType.MISSILE)
        drones = sum(1 for planned in self.pending_turn_spawns if planned.threat_type == ThreatType.DRONE)
        return missiles, drones

    def cycle_selected_target(self, step: int = 1) -> bool:
        if self.phase != TurnPhase.PLAYER_PLANNING:
            return False

        targets = self._targetable_assets()
        if not targets:
            self.selected_target_id = ""
            return False

        if self.selected_target_id not in {asset.asset_id for asset in targets}:
            self.selected_target_id = targets[0].asset_id
            return True

        current_index = next(
            i for i, asset in enumerate(targets) if asset.asset_id == self.selected_target_id
        )
        next_index = (current_index + step) % len(targets)
        self.selected_target_id = targets[next_index].asset_id
        return True

    def select_target_nearest(self, x: float, y: float, max_distance: float = 40.0) -> bool:
        if self.phase != TurnPhase.PLAYER_PLANNING:
            return False

        targets = self._targetable_assets()
        if not targets:
            self.selected_target_id = ""
            return False

        nearest = min(targets, key=lambda asset: ((asset.x - x) ** 2 + (asset.y - y) ** 2) ** 0.5)
        distance = ((nearest.x - x) ** 2 + (nearest.y - y) ** 2) ** 0.5
        if distance > max_distance:
            return False

        self.selected_target_id = nearest.asset_id
        return True

    def selected_target(self) -> Asset | None:
        self._sync_selected_target()
        return self._asset_by_id(self.selected_target_id)

    def selected_target_label(self) -> str:
        asset = self.selected_target()
        if asset is None:
            return "none"
        return asset.display_name if asset.display_name else asset.asset_id

    def queued_plan_lines(self, max_lines: int = 5) -> list[str]:
        counts: dict[str, dict[str, int]] = {}
        for planned in self.pending_turn_spawns:
            if planned.target_asset_id not in counts:
                counts[planned.target_asset_id] = {"missile": 0, "drone": 0}
            counts[planned.target_asset_id][planned.threat_type.value] += 1

        lines: list[str] = []
        for target_id, values in counts.items():
            asset = self._asset_by_id(target_id)
            label = target_id
            if asset is not None:
                label = asset.display_name if asset.display_name else asset.asset_id

            lines.append(f"{label}: M{values['missile']} D{values['drone']}")

        lines.sort()
        return lines[:max_lines]

    def is_mission_lost(self) -> bool:
        return not any(asset.kind == "base" and asset.is_alive() for asset in self.assets)

    def _build_assets(self) -> list[Asset]:
        if self.map_data is not None:
            by_name = {location.feature_name: location for location in self.map_data.locations}

            def from_location(
                asset_id: str,
                kind: str,
                location_name: str,
                hp: int,
                strategic_value: float,
            ) -> Asset | None:
                location = by_name.get(location_name)
                if location is None:
                    return None

                x_px, y_px = self.projector.to_screen(location.x_km, location.y_km)
                return Asset(
                    asset_id=asset_id,
                    kind=kind,
                    x=x_px,
                    y=y_px,
                    hp=hp,
                    max_hp=hp,
                    strategic_value=strategic_value,
                    side=location.side,
                    display_name=location.feature_name,
                )

            assets: list[Asset] = []
            candidates = [
                from_location("base_hq", "base", "Arktholm (Capital X)", 230, 1.0),
                from_location("ad_alpha", "air_defense", "Highridge Command", 140, 0.84),
                from_location(
                    "fighter_charlie",
                    "fighter_base",
                    "Northern Vanguard Base",
                    155,
                    0.86,
                ),
                from_location("drone_delta", "drone_hub", "Boreal Watch Post", 120, 0.63),
                from_location("city_nordvik", "city", "Nordvik", 100, 0.72),
                from_location("city_valbrek", "city", "Valbrek", 100, 0.74),
            ]
            assets.extend([asset for asset in candidates if asset is not None])

            if assets:
                return assets

        return [
            Asset(
                asset_id="base_hq",
                kind="base",
                x=self.width * 0.52,
                y=self.height * 0.82,
                hp=220,
                max_hp=220,
                strategic_value=1.0,
                side="north",
                display_name="HQ",
            ),
            Asset(
                asset_id="ad_alpha",
                kind="air_defense",
                x=self.width * 0.28,
                y=self.height * 0.80,
                hp=130,
                max_hp=130,
                strategic_value=0.82,
                side="north",
                display_name="AD Alpha",
            ),
            Asset(
                asset_id="fighter_charlie",
                kind="fighter_base",
                x=self.width * 0.78,
                y=self.height * 0.79,
                hp=150,
                max_hp=150,
                strategic_value=0.86,
                side="north",
                display_name="Fighter Charlie",
            ),
            Asset(
                asset_id="drone_delta",
                kind="drone_hub",
                x=self.width * 0.64,
                y=self.height * 0.90,
                hp=110,
                max_hp=110,
                strategic_value=0.60,
                side="north",
                display_name="Drone Delta",
            ),
        ]

    def _build_enemy_launch_points(self) -> list[tuple[float, float]]:
        if self.map_data is None:
            return []

        points: list[tuple[float, float]] = []
        for location in self.map_data.locations:
            if location.side == "south" and location.subtype == "air_base":
                points.append(self.projector.to_screen(location.x_km, location.y_km))

        return points

    def _spawn_threat(self, threat_type: ThreatType, target_asset_id: str) -> None:
        target = self._asset_by_id(target_asset_id)
        if target is None or not target.is_alive():
            fallback_targets = self._targetable_assets()
            if not fallback_targets:
                fallback_targets = [asset for asset in self.assets if asset.is_alive()]
            if not fallback_targets:
                return
            target = fallback_targets[0]

        if self.enemy_launch_points:
            base_x, base_y = self.rng.choice(self.enemy_launch_points)
            x = base_x + self.rng.uniform(-22.0, 22.0)
            y = base_y + self.rng.uniform(-12.0, 12.0)
        else:
            x = float(self.rng.uniform(35, self.width - 35))
            y = self.height + 24.0

        speed = self.rng.uniform(180, 240) if threat_type == ThreatType.MISSILE else self.rng.uniform(85, 130)
        dx = target.x - x
        dy = target.y - y
        distance = max((dx**2 + dy**2) ** 0.5, 1.0)
        vx = dx / distance * speed
        vy = dy / distance * speed

        threat = Threat(
            threat_id=self.next_threat_id,
            threat_type=threat_type,
            x=x,
            y=y,
            vx=vx,
            vy=vy,
            intended_target_id=target.asset_id,
        )
        self.next_threat_id += 1
        self.threats.append(threat)
        self._log(f"Detected {threat.threat_type.value} T{threat.threat_id} heading toward {target.asset_id}.")

    def _update_threats(self, dt: float) -> None:
        for threat in self.threats:
            if not threat.alive:
                continue

            threat.update(dt)

            if (
                threat.x < -80
                or threat.x > self.width + 80
                or threat.y < -80
                or threat.y > self.height + 80
            ):
                threat.alive = False
                threat.assigned = False
                self.impact_count += 1
                self._log(f"Threat T{threat.threat_id} escaped coverage and crossed defended zone.")
                continue

            target = self._asset_by_id(threat.intended_target_id)
            if target is None or not target.is_alive():
                continue

            if threat.distance_to(target.x, target.y) <= 16:
                damage = 45 if threat.threat_type == ThreatType.MISSILE else 12
                target.hp = max(0, target.hp - damage)
                threat.alive = False
                threat.assigned = False
                self.impact_count += 1

                if target.hp <= 0:
                    self._log(f"Impact: T{threat.threat_id} destroyed {target.asset_id} (-{damage} HP).")
                else:
                    self._log(f"Impact: T{threat.threat_id} hit {target.asset_id} (-{damage} HP).")

    def _start_ai_worker(self) -> None:
        with self._ai_result_lock:
            self._ai_result = None
            self._ai_error = None

        self._ai_thread = threading.Thread(target=self._analyze_turn_worker, daemon=True)
        self._ai_thread.start()

    def _analyze_turn_worker(self) -> None:
        try:
            active_threats = [threat for threat in self.threats if threat.alive]
            analyses = self.analyzer.analyze_turn_blocking(active_threats, self.assets)

            with self._ai_result_lock:
                self._ai_result = analyses
                self._ai_error = None
        except Exception as exc:  # pragma: no cover - defensive fallback
            with self._ai_result_lock:
                self._ai_result = {}
                self._ai_error = str(exc)

    def _poll_ai_result(self) -> None:
        if self._ai_thread is not None and self._ai_thread.is_alive():
            self.ai_provider_status = self.analyzer.provider_status
            return

        with self._ai_result_lock:
            analyses = self._ai_result or {}
            ai_error = self._ai_error

        if ai_error:
            self._log(f"AI analysis fallback active: {ai_error}")

        self.turn_analyses = analyses
        self._refresh_ai_json(analyses)
        self.ai_provider_status = self.analyzer.provider_status
        self.phase = TurnPhase.RESOLVING
        self._ai_thread = None

        self._log(f"AI analysis ready. Resolving turn {self.turn_number}.")

    def _execute_decisions(self, decisions: list[Decision]) -> None:
        for decision in decisions:
            threat = self._threat_by_id(decision.threat_id)
            if threat is None or not threat.alive or threat.assigned:
                continue

            source = self._asset_by_id(decision.launch_from)
            if source is None or not source.is_alive():
                continue

            # -------------------------
            # AIR DEFENSE (WITH RADIUS)
            # -------------------------
            if decision.action == DecisionAction.ENGAGE_AIR_DEFENSE:
                if self.resources.consume_air_defense(
                    source.x,
                    source.y,
                    threat.x,
                    threat.y
                ):
                    self._launch_interceptor(decision, threat)
                    threat.assigned = True
                    self._log(
                        f"Decision: AD engaged T{threat.threat_id} from {decision.launch_from}"
                        f" (score={decision.priority_score:.2f})."
                    )

            # -------------------------
            # FIGHTER
            # -------------------------
            elif decision.action == DecisionAction.SCRAMBLE_FIGHTER:
                if self.resources.launch_fighter():
                    self._launch_interceptor(decision, threat)
                    threat.assigned = True
                    self._log(
                        f"Decision: Fighter scrambled for T{threat.threat_id} from {decision.launch_from}"
                        f" (score={decision.priority_score:.2f})."
                    )
                elif self.resources.fuel <= 0:
                    self._log("Decision blocked: No fuel available for fighter launch.")

            # -------------------------
            # DRONE
            # -------------------------
            elif decision.action == DecisionAction.DEPLOY_DRONE:
                if self.resources.launch_drone():
                    self._launch_interceptor(decision, threat)
                    threat.assigned = True
                    self._log(
                        f"Decision: Drone deployed for T{threat.threat_id} from {decision.launch_from}"
                        f" (score={decision.priority_score:.2f})."
                    )

            # HOLD = do nothing on purpose

    def _launch_interceptor(self, decision: Decision, threat: Threat) -> None:
        source = self._asset_by_id(decision.launch_from)
        if source is None:
            source = next((asset for asset in self.assets if asset.is_alive()), None)
        if source is None:
            return

        if decision.action == DecisionAction.ENGAGE_AIR_DEFENSE:
            interceptor_type = InterceptorType.AIR_DEFENSE
            speed = 365.0
            remaining_engagements = 1
        elif decision.action == DecisionAction.SCRAMBLE_FIGHTER:
            interceptor_type = InterceptorType.FIGHTER
            speed = 275.0
            remaining_engagements = 3
        else:
            interceptor_type = InterceptorType.DRONE
            speed = 205.0
            remaining_engagements = 1

        interceptor = Interceptor(
            interceptor_id=self.next_interceptor_id,
            interceptor_type=interceptor_type,
            source_id=source.asset_id,
            target_threat_id=threat.threat_id,
            x=source.x,
            y=source.y,
            speed=speed,
            remaining_engagements=remaining_engagements,
        )

        self.next_interceptor_id += 1
        self.interceptors.append(interceptor)

    def _update_interceptors(self, dt: float) -> None:
        for interceptor in self.interceptors:
            if not interceptor.alive:
                continue

            if interceptor.interceptor_type == InterceptorType.FIGHTER:
                self._update_fighter_interceptor(interceptor, dt)
                continue

            threat = self._threat_by_id(interceptor.target_threat_id)
            if threat is None or not threat.alive:
                interceptor.alive = False
                continue

            reached = interceptor.update_toward(threat.x, threat.y, dt)
            if not reached:
                continue

            kill_probability = self._kill_probability(interceptor.interceptor_type, threat.threat_type)
            if self.rng.random() <= kill_probability:
                threat.alive = False
                threat.assigned = False
                self.neutralized_count += 1
                self._log(
                    f"Neutralized: T{threat.threat_id} by {interceptor.interceptor_type.value}"
                    f" (p={kill_probability:.2f})."
                )
            else:
                threat.assigned = False
                self._log(
                    f"Miss: {interceptor.interceptor_type.value} failed on T{threat.threat_id}"
                    f" (p={kill_probability:.2f})."
                )

            interceptor.alive = False

    def _update_fighter_interceptor(self, interceptor: Interceptor, dt: float) -> None:
        if interceptor.returning:
            home = self._asset_by_id(interceptor.source_id)
            if home is None or not home.is_alive():
                interceptor.alive = False
                self.resources.recover_fighter()
                return

            if interceptor.update_toward(home.x, home.y, dt):
                interceptor.alive = False
                self.resources.recover_fighter()
                self._log(f"Fighter returned to {home.asset_id}.")
            return

        threat = self._threat_by_id(interceptor.target_threat_id)
        if threat is None or not threat.alive:
            next_threat = self._nearest_unassigned_threat(interceptor.x, interceptor.y)
            if next_threat is None:
                interceptor.returning = True
                self._log("Fighter returning (no remaining threats).")
                return

            interceptor.target_threat_id = next_threat.threat_id
            next_threat.assigned = True
            threat = next_threat

        reached = interceptor.update_toward(threat.x, threat.y, dt)
        if not reached:
            return

        kill_probability = self._kill_probability(interceptor.interceptor_type, threat.threat_type)
        if self.rng.random() <= kill_probability:
            threat.alive = False
            threat.assigned = False
            self.neutralized_count += 1
            self._log(f"Neutralized: T{threat.threat_id} by fighter (p={kill_probability:.2f}).")
        else:
            threat.assigned = False
            self._log(f"Miss: fighter failed on T{threat.threat_id} (p={kill_probability:.2f}).")

        interceptor.remaining_engagements -= 1
        if interceptor.remaining_engagements <= 0:
            interceptor.returning = True
            self._log("Fighter returning (max engagements reached).")
            return

        if threat.alive:
            threat.assigned = True
            return

        next_threat = self._nearest_unassigned_threat(interceptor.x, interceptor.y)
        if next_threat is None:
            interceptor.returning = True
            self._log("Fighter returning (no remaining threats).")
            return

        interceptor.target_threat_id = next_threat.threat_id
        next_threat.assigned = True

    def _nearest_unassigned_threat(self, x: float, y: float) -> Threat | None:
        candidates = [threat for threat in self.threats if threat.alive and not threat.assigned]
        if not candidates:
            return None
        return min(candidates, key=lambda threat: threat.distance_to(x, y))

    def _kill_probability(self, interceptor_type: InterceptorType, threat_type: ThreatType) -> float:
        table = {
            InterceptorType.AIR_DEFENSE: {
                ThreatType.MISSILE: 0.88,
                ThreatType.DRONE: 0.65,
            },
            InterceptorType.FIGHTER: {
                ThreatType.MISSILE: 0.77,
                ThreatType.DRONE: 0.86,
            },
            InterceptorType.DRONE: {
                ThreatType.MISSILE: 0.15,
                ThreatType.DRONE: 0.55,
            },
        }
        return table[interceptor_type][threat_type]

    def _refresh_ai_json(self, analyses: dict[int, ThreatAnalysis]) -> None:
        ranked = sorted(analyses.values(), key=lambda item: item.urgency, reverse=True)
        self.latest_ai_json = [
            json.dumps(item.to_json(), separators=(",", ":")) for item in ranked[:3]
        ]

    def _purge_destroyed_objects(self) -> None:
        self.threats = [threat for threat in self.threats if threat.alive]
        self.interceptors = [interceptor for interceptor in self.interceptors if interceptor.alive]

    def _targetable_assets(self) -> list[Asset]:
        return [
            asset
            for asset in self.assets
            if asset.is_alive()
            and (asset.side == "north" or asset.side == "")
            and asset.kind in {"base", "air_defense", "fighter_base", "drone_hub"}
        ]

    def _is_targetable_asset_id(self, asset_id: str) -> bool:
        return any(asset.asset_id == asset_id for asset in self._targetable_assets())

    def _sync_selected_target(self) -> None:
        targetable = self._targetable_assets()
        if not targetable:
            self.selected_target_id = ""
            return

        if self.selected_target_id and any(asset.asset_id == self.selected_target_id for asset in targetable):
            return

        self.selected_target_id = targetable[0].asset_id

    def _asset_by_id(self, asset_id: str) -> Asset | None:
        return next((asset for asset in self.assets if asset.asset_id == asset_id), None)

    def _threat_by_id(self, threat_id: int) -> Threat | None:
        return next((threat for threat in self.threats if threat.threat_id == threat_id), None)

    def _log(self, message: str) -> None:
        timestamp = f"T+{self.time_elapsed:05.1f}s"
        self.event_log.appendleft(f"{timestamp} {message}")
