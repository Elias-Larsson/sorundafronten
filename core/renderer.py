from __future__ import annotations

import pygame

from core.decision_engine import DecisionAction
from core.map_loader import MapData, MapProjector, load_svg_background
from core.simulation import Simulation
from models import InterceptorType, ThreatType


class Renderer:
    def __init__(
        self,
        width: int,
        height: int,
        map_data: MapData | None = None,
        projector: MapProjector | None = None,
    ):
        self.width = width
        self.height = height
        self.map_data = map_data
        self.projector = projector

        self.title_font = pygame.font.SysFont("consolas", 22, bold=True)
        self.main_font = pygame.font.SysFont("consolas", 17)
        self.small_font = pygame.font.SysFont("consolas", 14)

        self.background = pygame.Surface((width, height))
        self.map_source_label = "generated background"
        self._build_background()

    def draw(self, surface: pygame.Surface, simulation: Simulation) -> None:
        surface.blit(self.background, (0, 0))

        self._draw_assets(surface, simulation)
        self._draw_selected_target(surface, simulation)
        self._draw_threats(surface, simulation)
        self._draw_interceptors(surface, simulation)
        self._draw_hud(surface, simulation)

        if simulation.is_mission_lost():
            self._draw_mission_lost(surface)

    def _build_background(self) -> None:
        self.background.fill((15, 30, 46))

        if self.map_data is not None and self.projector is not None:
            map_rect = pygame.Rect(
                int(round(self.projector.offset_x)),
                int(round(self.projector.offset_y)),
                int(round(self.projector.pixel_width)),
                int(round(self.projector.pixel_height)),
            )
            pygame.draw.rect(self.background, (12, 22, 34), map_rect)

            svg_surface = load_svg_background(self.map_data.svg_path, self.projector)
            if svg_surface is not None:
                self.background.blit(svg_surface, map_rect.topleft)
                self.map_source_label = "map.svg + map.csv coordinates"
            else:
                self._draw_csv_terrain(self.background)
                self.map_source_label = "map.csv terrain fallback"

            pygame.draw.rect(self.background, (188, 211, 231), map_rect, 1)
            return

        self._draw_generated_background()

    def _draw_generated_background(self) -> None:
        top = (10, 22, 48)
        middle = (22, 45, 74)
        bottom = (37, 72, 54)

        for y in range(self.height):
            t = y / max(1, self.height - 1)
            if t < 0.6:
                k = t / 0.6
                color = (
                    int(top[0] + (middle[0] - top[0]) * k),
                    int(top[1] + (middle[1] - top[1]) * k),
                    int(top[2] + (middle[2] - top[2]) * k),
                )
            else:
                k = (t - 0.6) / 0.4
                color = (
                    int(middle[0] + (bottom[0] - middle[0]) * k),
                    int(middle[1] + (bottom[1] - middle[1]) * k),
                    int(middle[2] + (bottom[2] - middle[2]) * k),
                )

            pygame.draw.line(self.background, color, (0, y), (self.width, y))

        pygame.draw.rect(
            self.background,
            (44, 62, 46),
            pygame.Rect(0, int(self.height * 0.86), self.width, int(self.height * 0.14)),
        )

    def _draw_csv_terrain(self, surface: pygame.Surface) -> None:
        if self.map_data is None or self.projector is None:
            return

        for terrain in self.map_data.terrains:
            if len(terrain.points_km) < 3:
                continue

            points = self.projector.polygon_to_screen(terrain.points_km)
            if terrain.side == "north":
                color = (48, 78, 50)
            else:
                color = (88, 74, 52)

            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, (24, 32, 38), points, 1)

    def _draw_assets(self, surface: pygame.Surface, simulation: Simulation) -> None:
        for asset in simulation.assets:
            x = int(asset.x)
            y = int(asset.y)
            alive = asset.is_alive()

            if asset.kind == "base":
                color = (75, 165, 250) if alive else (70, 70, 70)
                pygame.draw.rect(surface, color, pygame.Rect(x - 32, y - 18, 64, 36), border_radius=6)
                label = "HQ"
            elif asset.kind == "air_defense":
                color = (102, 231, 123) if alive else (70, 70, 70)
                pygame.draw.polygon(
                    surface,
                    color,
                    [(x, y - 23), (x - 22, y + 16), (x + 22, y + 16)],
                )
                label = "AD"
            elif asset.kind == "fighter_base":
                color = (130, 196, 255) if alive else (70, 70, 70)
                pygame.draw.circle(surface, color, (x, y), 22)
                label = "FTR"
            else:
                color = (255, 208, 110) if alive else (70, 70, 70)
                pygame.draw.polygon(
                    surface,
                    color,
                    [(x, y - 18), (x - 18, y), (x, y + 18), (x + 18, y)],
                )
                label = "DRV"

            name = asset.display_name if asset.display_name else asset.asset_id
            text = self.small_font.render(f"{name} ({label})", True, (240, 245, 252))
            surface.blit(text, (x - text.get_width() // 2, y + 24))

            ratio = 0.0 if asset.max_hp <= 0 else max(0.0, asset.hp / asset.max_hp)
            bar_width = 66
            bar_x = x - bar_width // 2
            bar_y = y - 34
            pygame.draw.rect(surface, (35, 45, 56), pygame.Rect(bar_x, bar_y, bar_width, 6), border_radius=3)
            pygame.draw.rect(
                surface,
                (104, 233, 131),
                pygame.Rect(bar_x, bar_y, int(bar_width * ratio), 6),
                border_radius=3,
            )

    def _draw_threats(self, surface: pygame.Surface, simulation: Simulation) -> None:
        for threat in simulation.threats:
            x = int(threat.x)
            y = int(threat.y)
            if threat.threat_type == ThreatType.MISSILE:
                pygame.draw.polygon(surface, (246, 74, 74), [(x, y - 10), (x - 6, y + 8), (x + 6, y + 8)])
            else:
                pygame.draw.circle(surface, (248, 187, 70), (x, y), 7)
                pygame.draw.circle(surface, (80, 58, 20), (x, y), 8, 1)

            marker = self.small_font.render(f"T{threat.threat_id}", True, (246, 246, 246))
            surface.blit(marker, (x - marker.get_width() // 2, y - 24))

    def _draw_selected_target(self, surface: pygame.Surface, simulation: Simulation) -> None:
        target = simulation.selected_target()
        if target is None:
            return

        x = int(target.x)
        y = int(target.y)
        pygame.draw.circle(surface, (255, 229, 128), (x, y), 32, 2)
        pygame.draw.circle(surface, (255, 247, 196), (x, y), 39, 1)

        label = self.small_font.render("SELECTED TARGET", True, (255, 246, 202))
        surface.blit(label, (x - label.get_width() // 2, y - 54))

    def _draw_interceptors(self, surface: pygame.Surface, simulation: Simulation) -> None:
        for interceptor in simulation.interceptors:
            x = int(interceptor.x)
            y = int(interceptor.y)

            if interceptor.interceptor_type == InterceptorType.AIR_DEFENSE:
                pygame.draw.circle(surface, (119, 255, 144), (x, y), 4)
            elif interceptor.interceptor_type == InterceptorType.FIGHTER:
                pygame.draw.polygon(surface, (235, 246, 255), [(x, y - 7), (x - 5, y + 5), (x + 5, y + 5)])
            else:
                pygame.draw.circle(surface, (150, 229, 222), (x, y), 5)
                pygame.draw.circle(surface, (38, 87, 82), (x, y), 6, 1)

    def _draw_hud(self, surface: pygame.Surface, simulation: Simulation) -> None:
        panel_width = 440
        panel = pygame.Surface((panel_width, self.height - 20), pygame.SRCALPHA)
        panel.fill((10, 18, 27, 200))
        panel_x = self.width - panel_width - 10
        panel_y = 10
        surface.blit(panel, (panel_x, panel_y))

        x = panel_x + 14
        y = panel_y + 12

        title = self.title_font.render("Hybrid Air Defense Prototype", True, (242, 248, 255))
        surface.blit(title, (x, y))
        y += 34

        missiles_queued, drones_queued = simulation.queued_counts()

        stats = [
            f"Turn: {simulation.turn_number}",
            f"Phase: {simulation.phase_label()}",
            f"Selected Target: {simulation.selected_target_label()}",
            f"Time: {simulation.time_elapsed:5.1f}s",
            f"Neutralized: {simulation.neutralized_count}",
            f"Impacts/Leaks: {simulation.impact_count}",
            f"AD Ammo: {simulation.resources.air_defense_ammo}",
            f"Fighters: {simulation.resources.fighters_available}/{simulation.resources.fighters_total}",            
            f"Drones Ready: {simulation.resources.drones_ready}",
            f"Queued Missiles: {missiles_queued}",
            f"Queued Drones: {drones_queued}",
            f"AI Source: {simulation.ai_provider_status}",
            f"Map Source: {self.map_source_label}",
        ]
        for line in stats:
            text = self.main_font.render(line, True, (216, 232, 245))
            surface.blit(text, (x, y))
            y += 22

        y += 6
        queue_title = self.main_font.render("Queued attacks by target", True, (255, 228, 173))
        surface.blit(queue_title, (x, y))
        y += 22

        queued_lines = simulation.queued_plan_lines(max_lines=5)
        if not queued_lines:
            text = self.small_font.render("No queued attacks", True, (237, 223, 193))
            surface.blit(text, (x, y))
            y += 18
        else:
            for line in queued_lines:
                text = self.small_font.render(line, True, (237, 223, 193))
                surface.blit(text, (x, y))
                y += 18

        y += 6
        decisions_title = self.main_font.render("Latest deterministic decisions", True, (171, 216, 255))
        surface.blit(decisions_title, (x, y))
        y += 24

        action_label = {
            DecisionAction.ENGAGE_AIR_DEFENSE: "AD",
            DecisionAction.SCRAMBLE_FIGHTER: "FTR",
            DecisionAction.DEPLOY_DRONE: "DRV",
            DecisionAction.HOLD: "HOLD",
        }

        for decision in simulation.latest_decisions[:4]:
            line = (
                f"{action_label[decision.action]} T{decision.threat_id}"
                f" score={decision.priority_score:.2f} from {decision.launch_from}"
            )
            text = self.small_font.render(line, True, (240, 248, 255))
            surface.blit(text, (x, y))
            y += 18

        y += 6
        ai_title = self.main_font.render("AI analysis JSON (non-decision)", True, (174, 228, 197))
        surface.blit(ai_title, (x, y))
        y += 24

        for line in simulation.latest_ai_json[:3]:
            text = self.small_font.render(line, True, (204, 237, 220))
            surface.blit(text, (x, y))
            y += 18

        y += 6
        event_title = self.main_font.render("Event log", True, (243, 217, 170))
        surface.blit(event_title, (x, y))
        y += 22

        for entry in list(simulation.event_log)[:7]:
            text = self.small_font.render(entry, True, (247, 236, 214))
            surface.blit(text, (x, y))
            y += 18

        if simulation.is_player_turn():
            controls = self.small_font.render(
                "Planning: M missile | D drone | LEFT/RIGHT switch target | C clear | ENTER start",
                True,
                (216, 233, 248),
            )
        else:
            controls = self.small_font.render(
                "Turn in progress: waiting for Gemini or resolving engagements | ESC quit",
                True,
                (216, 233, 248),
            )
        surface.blit(controls, (14, self.height - 24))

    def _draw_mission_lost(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((20, 5, 5, 120))
        surface.blit(overlay, (0, 0))

        text = self.title_font.render("MISSION LOST: Base destroyed", True, (255, 211, 211))
        surface.blit(text, (self.width // 2 - text.get_width() // 2, self.height // 2 - 12))
