from __future__ import annotations

from pathlib import Path

import pygame

from core.map_loader import MapProjector, load_map_data
from core.renderer import Renderer
from core.simulation import Simulation
from models import ThreatType

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in minimal setups
    load_dotenv = None


WIDTH = 1280
HEIGHT = 720


def main() -> None:
    project_root = Path(__file__).resolve().parent
    if load_dotenv is not None:
        load_dotenv(project_root / ".env")

    pygame.init()
    pygame.display.set_caption("Intelligent Air Defense Decision Support Prototype")

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    map_data = load_map_data(project_root / "map.csv", project_root / "map.svg")
    projector = MapProjector(
        map_data.world_width_km,
        map_data.world_height_km,
        WIDTH,
        HEIGHT,
    )

    simulation = Simulation(WIDTH, HEIGHT, map_data=map_data, projector=projector)
    renderer = Renderer(WIDTH, HEIGHT, map_data=map_data, projector=projector)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif simulation.is_player_turn():
                    if event.key == pygame.K_m:
                        simulation.spawn_manual(ThreatType.MISSILE)
                    elif event.key == pygame.K_d:
                        simulation.spawn_manual(ThreatType.DRONE)
                    elif event.key in (pygame.K_LEFT, pygame.K_q):
                        simulation.cycle_selected_target(-1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_e, pygame.K_TAB):
                        simulation.cycle_selected_target(1)
                    elif event.key == pygame.K_c:
                        simulation.clear_planned_threats()
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        simulation.start_turn()

            elif event.type == pygame.MOUSEBUTTONDOWN and simulation.is_player_turn():
                x, _ = pygame.mouse.get_pos()
                if event.button in (1, 3):
                    simulation.select_target_nearest(float(x), float(y))

        simulation.update(dt)
        renderer.draw(screen, simulation)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
