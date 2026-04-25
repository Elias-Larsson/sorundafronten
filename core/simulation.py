from __future__ import annotations

from collections import deque
import json
import random
from pathlib import Path
from typing import Deque

from ai import ThreatAnalysis, ThreatAnalyzer
from core.decision_engine import Decision, DecisionAction, DecisionEngine
from core.map_loader import MapData, MapProjector, load_map_data
from models import Asset, Interceptor, InterceptorType, ResourceState, Threat, ThreatType


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

        self.threats: list[Threat] = []
        self.interceptors: list[Interceptor] = []

        self.time_elapsed = 0.0
        self.spawn_timer = 0.0
        self.base_spawn_interval = 1.9

        self.next_threat_id = 1
        self.next_interceptor_id = 1

        self.latest_ai_json: list[str] = []
        self.latest_decisions: list[Decision] = []
        self.event_log: Deque[str] = deque(maxlen=12)

        self.neutralized_count = 0
        self.impact_count = 0

    def update(self, dt: float) -> None:
        self.time_elapsed += dt
        self.resources.tick(dt)

        self._spawn_logic(dt)
        self._update_threats(dt)

        analyses = self._analyze_active_threats()
        self.latest_decisions = self.decision_engine.decide(
            threats=self.threats,
            analyses=analyses,
            resources=self.resources,
            assets=self.assets,
        )

        self._execute_decisions(self.latest_decisions)
        self._update_interceptors(dt)
        self._refresh_ai_json(analyses)
        self._purge_destroyed_objects()

    def spawn_manual(self, threat_type: ThreatType, spawn_x: float | None = None) -> None:
        self._spawn_threat(threat_type, spawn_x)

    def spawn_wave(self) -> None:
        wave_size = self.rng.randint(3, 5)
        for _ in range(wave_size):
            threat_type = ThreatType.MISSILE if self.rng.random() < 0.45 else ThreatType.DRONE
            self._spawn_threat(threat_type)

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

    def _spawn_logic(self, dt: float) -> None:
        interval = max(1.0, self.base_spawn_interval - min(0.9, self.time_elapsed / 120.0))
        self.spawn_timer += dt

        if self.spawn_timer < interval:
            return

        self.spawn_timer = 0.0
        self._spawn_threat(ThreatType.MISSILE if self.rng.random() < 0.45 else ThreatType.DRONE)

        # Occasional second threat to force parallel prioritization decisions.
        if self.rng.random() < 0.28:
            self._spawn_threat(ThreatType.MISSILE if self.rng.random() < 0.35 else ThreatType.DRONE)

    def _spawn_threat(self, threat_type: ThreatType, spawn_x: float | None = None) -> None:
        defended_assets = [
            asset for asset in self.assets if asset.is_alive() and (asset.side == "north" or not asset.side)
        ]
        if not defended_assets:
            defended_assets = [asset for asset in self.assets if asset.is_alive()]

        if not defended_assets:
            return

        if spawn_x is not None:
            x = float(spawn_x)
            y = self.height + 24.0
        elif self.enemy_launch_points:
            base_x, base_y = self.rng.choice(self.enemy_launch_points)
            x = base_x + self.rng.uniform(-22.0, 22.0)
            y = base_y + self.rng.uniform(-12.0, 12.0)
        else:
            x = float(self.rng.uniform(35, self.width - 35))
            y = self.height + 24.0

        target = self.rng.choices(
            defended_assets,
            weights=[asset.strategic_value for asset in defended_assets],
            k=1,
        )[0]

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

    def _analyze_active_threats(self) -> dict[int, ThreatAnalysis]:
        active_threats = [threat for threat in self.threats if threat.alive]
        analyses = self.analyzer.analyze_all(active_threats, self.assets)
        self.ai_provider_status = self.analyzer.provider_status
        return analyses

    def _execute_decisions(self, decisions: list[Decision]) -> None:
        for decision in decisions:
            threat = self._threat_by_id(decision.threat_id)
            if threat is None or not threat.alive or threat.assigned:
                continue

            if decision.action == DecisionAction.ENGAGE_AIR_DEFENSE:
                if self.resources.consume_air_defense():
                    self._launch_interceptor(decision, threat)
                    threat.assigned = True
                    self._log(
                        f"Decision: AD engaged T{threat.threat_id} from {decision.launch_from}"
                        f" (score={decision.priority_score:.2f})."
                    )

            elif decision.action == DecisionAction.SCRAMBLE_FIGHTER:
                if self.resources.launch_fighter():
                    self._launch_interceptor(decision, threat)
                    threat.assigned = True
                    self._log(
                        f"Decision: Fighter scrambled for T{threat.threat_id} from {decision.launch_from}"
                        f" (score={decision.priority_score:.2f})."
                    )

            elif decision.action == DecisionAction.DEPLOY_DRONE:
                if self.resources.launch_drone():
                    self._launch_interceptor(decision, threat)
                    threat.assigned = True
                    self._log(
                        f"Decision: Drone deployed for T{threat.threat_id} from {decision.launch_from}"
                        f" (score={decision.priority_score:.2f})."
                    )

            # HOLD decisions are intentional non-actions and stay in the on-screen rationale list.

    def _launch_interceptor(self, decision: Decision, threat: Threat) -> None:
        source = self._asset_by_id(decision.launch_from)
        if source is None:
            source = next((asset for asset in self.assets if asset.is_alive()), None)
        if source is None:
            return

        if decision.action == DecisionAction.ENGAGE_AIR_DEFENSE:
            interceptor_type = InterceptorType.AIR_DEFENSE
            speed = 365.0
        elif decision.action == DecisionAction.SCRAMBLE_FIGHTER:
            interceptor_type = InterceptorType.FIGHTER
            speed = 275.0
        else:
            interceptor_type = InterceptorType.DRONE
            speed = 205.0

        interceptor = Interceptor(
            interceptor_id=self.next_interceptor_id,
            interceptor_type=interceptor_type,
            source_id=source.asset_id,
            target_threat_id=threat.threat_id,
            x=source.x,
            y=source.y,
            speed=speed,
        )

        self.next_interceptor_id += 1
        self.interceptors.append(interceptor)

    def _update_interceptors(self, dt: float) -> None:
        for interceptor in self.interceptors:
            if not interceptor.alive:
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

    def _asset_by_id(self, asset_id: str) -> Asset | None:
        return next((asset for asset in self.assets if asset.asset_id == asset_id), None)

    def _threat_by_id(self, threat_id: int) -> Threat | None:
        return next((threat for threat in self.threats if threat.threat_id == threat_id), None)

    def _log(self, message: str) -> None:
        timestamp = f"T+{self.time_elapsed:05.1f}s"
        self.event_log.appendleft(f"{timestamp} {message}")
