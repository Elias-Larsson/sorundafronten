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

        # Layout
        self.hud_width = 360
        self.map_width = width - self.hud_width

        self.map_data = map_data
        self.projector = projector

        self.title_font = pygame.font.SysFont("consolas", 22, bold=True)
        self.main_font = pygame.font.SysFont("consolas", 17)
        self.small_font = pygame.font.SysFont("consolas", 14)

        self.background = pygame.Surface((self.map_width, height))
        self.map_source_label = "generated background"
        self._build_background()

    # =========================================================
    # MAIN DRAW
    # =========================================================
    def draw(self, surface: pygame.Surface, simulation: Simulation) -> None:
        # --- MAP AREA ---
        surface.blit(self.background, (0, 0))

        surface.set_clip(pygame.Rect(0, 0, self.map_width, self.height))

        self._draw_assets(surface, simulation)
        self._draw_selected_target(surface, simulation)
        self._draw_threats(surface, simulation)
        self._draw_interceptors(surface, simulation)
        self._draw_queued_on_map(surface, simulation)

        surface.set_clip(None)

        # --- HUD PANEL ---
        pygame.draw.rect(
            surface,
            (10, 18, 27),
            pygame.Rect(self.map_width, 0, self.hud_width, self.height),
        )

        pygame.draw.line(
            surface,
            (80, 100, 120),
            (self.map_width, 0),
            (self.map_width, self.height),
            2,
        )

        self._draw_hud(surface, simulation)

        if simulation.is_mission_lost():
            self._draw_mission_lost(surface)

    # =========================================================
    # BACKGROUND
    # =========================================================
    def _build_background(self) -> None:
        self.background.fill((15, 30, 46))

        if self.map_data and self.projector:
            map_rect = pygame.Rect(
                int(self.projector.offset_x),
                int(self.projector.offset_y),
                int(self.projector.pixel_width),
                int(self.projector.pixel_height),
            )

            pygame.draw.rect(self.background, (12, 22, 34), map_rect)

            svg_surface = load_svg_background(self.map_data.svg_path, self.projector)
            if svg_surface:
                self.background.blit(svg_surface, map_rect.topleft)
                self.map_source_label = "map.svg"
            else:
                self.map_source_label = "generated"

            pygame.draw.rect(self.background, (188, 211, 231), map_rect, 1)
            return

        for y in range(self.height):
            t = y / max(1, self.height)
            color = (
                int(10 + 40 * t),
                int(22 + 60 * t),
                int(48 + 30 * t),
            )
            pygame.draw.line(self.background, color, (0, y), (self.map_width, y))

    # =========================================================
    # DRAW ASSETS (WITH HEALTH)
    # =========================================================
    def _draw_assets(self, surface, simulation):
        for asset in simulation.assets:
            x, y = int(asset.x), int(asset.y)
            alive = asset.is_alive()

            if asset.kind == "base":
                color = (75, 165, 250) if alive else (70, 70, 70)
                pygame.draw.rect(surface, color, (x - 28, y - 16, 56, 32), border_radius=6)
                label = "Huvudstad"

            elif asset.kind == "air_defense":
                color = (102, 231, 123) if alive else (70, 70, 70)
                pygame.draw.polygon(surface, color, [(x, y - 20), (x - 18, y + 14), (x + 18, y + 14)])
                label = "Luftförsvar"

            elif asset.kind == "fighter_base":
                color = (130, 196, 255) if alive else (70, 70, 70)
                pygame.draw.circle(surface, color, (x, y), 18)
                label = "Flygbas"

            else:
                color = (255, 208, 110) if alive else (70, 70, 70)
                pygame.draw.polygon(surface, color, [(x, y - 14), (x - 14, y), (x, y + 14), (x + 14, y)])
                label = "Stad"

            # Name
            text = self.small_font.render(f"{label}", True, (240, 245, 252))
            surface.blit(text, (x - text.get_width() // 2, y + 22))

            # Health bar
            if asset.max_hp > 0:
                ratio = max(0.0, asset.hp / asset.max_hp)

                bar_width = 60
                bar_x = x - bar_width // 2
                bar_y = y - 28

                pygame.draw.rect(surface, (40, 50, 60), (bar_x, bar_y, bar_width, 6), border_radius=3)
                pygame.draw.rect(
                    surface,
                    (100, 230, 120),
                    (bar_x, bar_y, int(bar_width * ratio), 6),
                    border_radius=3,
                )

    # =========================================================
    # QUEUED ATTACKS ON MAP
    # =========================================================
    def _draw_queued_on_map(self, surface, simulation):
        if not simulation.is_player_turn():
            return

        counts = {}
        for planned in simulation.pending_turn_spawns:
            if planned.target_asset_id not in counts:
                counts[planned.target_asset_id] = {"missile": 0, "drone": 0}
            counts[planned.target_asset_id][planned.threat_type.value] += 1

        for asset in simulation.assets:
            if asset.asset_id not in counts:
                continue

            data = counts[asset.asset_id]
            text_str = f"M{data['missile']} D{data['drone']}"

            text = self.small_font.render(text_str, True, (255, 220, 120))
            surface.blit(text, (int(asset.x) - text.get_width() // 2, int(asset.y) - 45))

    # =========================================================
    # THREATS
    # =========================================================
    def _draw_threats(self, surface, simulation):
        for t in simulation.threats:
            x, y = int(t.x), int(t.y)
            if t.threat_type == ThreatType.MISSILE:
                pygame.draw.circle(surface, (255, 80, 80), (x, y), 6)
            else:
                pygame.draw.circle(surface, (255, 200, 100), (x, y), 5)

    # =========================================================
    # INTERCEPTORS
    # =========================================================
    def _draw_interceptors(self, surface, simulation):
        for i in simulation.interceptors:
            x, y = int(i.x), int(i.y)

            if i.interceptor_type == InterceptorType.AIR_DEFENSE:
                pygame.draw.circle(surface, (120, 255, 140), (x, y), 4)
            elif i.interceptor_type == InterceptorType.FIGHTER:
                pygame.draw.polygon(surface, (230, 240, 255), [(x, y - 6), (x - 5, y + 5), (x + 5, y + 5)])
            else:
                pygame.draw.circle(surface, (150, 229, 222), (x, y), 4)

    # =========================================================
    # SELECTED TARGET
    # =========================================================
    def _draw_selected_target(self, surface, simulation):
        target = simulation.selected_target()
        if not target:
            return

        pygame.draw.circle(surface, (255, 255, 150), (int(target.x), int(target.y)), 30, 2)

    # =========================================================
    # HUD
    # =========================================================
    def _draw_hud(self, surface, simulation):
        x = self.map_width + 14
        y = 14

        title = self.title_font.render("Air Defense System", True, (240, 248, 255))
        surface.blit(title, (x, y))
        y += 34

        stats = [
            f"Turn: {simulation.turn_number}",
            f"Phase: {simulation.phase_label()}",
            f"Time: {simulation.time_elapsed:.1f}s",
            "",
            f"AD Ammo: {simulation.resources.air_defense_ammo}",
            f"Fighters: {simulation.resources.fighters_available}/{simulation.resources.fighters_total}",
            f"Drones: {simulation.resources.drones_ready}",
            "",
            f"Neutralized: {simulation.neutralized_count}",
            f"Impacts: {simulation.impact_count}",
        ]

        for line in stats:
            text = self.main_font.render(line, True, (200, 220, 240))
            surface.blit(text, (x, y))
            y += 22

        y += 10

        # Decisions
        title = self.main_font.render("Decisions", True, (150, 200, 255))
        surface.blit(title, (x, y))
        y += 24

        for d in simulation.latest_decisions[:5]:
            text = self.small_font.render(
                f"{d.action.value} T{d.threat_id}", True, (220, 240, 255)
            )
            surface.blit(text, (x, y))
            y += 18

        y += 10

        # AI
        title = self.main_font.render("AI Analysis", True, (150, 255, 200))
        surface.blit(title, (x, y))
        y += 24

        for line in simulation.latest_ai_json[:3]:
            text = self.small_font.render(line, True, (200, 255, 220))
            surface.blit(text, (x, y))
            y += 18

    # =========================================================
    # MISSION LOST
    # =========================================================
    def _draw_mission_lost(self, surface):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((20, 0, 0, 120))
        surface.blit(overlay, (0, 0))

        text = self.title_font.render("MISSION LOST", True, (255, 200, 200))
        surface.blit(text, (self.width // 2 - text.get_width() // 2, self.height // 2))