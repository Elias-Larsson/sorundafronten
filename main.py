from __future__ import annotations

import pygame

from core.renderer import Renderer
from core.simulation import Simulation
from models import ThreatType


WIDTH = 1280
HEIGHT = 720


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Intelligent Air Defense Decision Support Prototype")

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    simulation = Simulation(WIDTH, HEIGHT)
    renderer = Renderer(WIDTH, HEIGHT)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_m:
                    simulation.spawn_manual(ThreatType.MISSILE)
                elif event.key == pygame.K_d:
                    simulation.spawn_manual(ThreatType.DRONE)
                elif event.key == pygame.K_w:
                    simulation.spawn_wave()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, _ = pygame.mouse.get_pos()
                if event.button == 1:
                    simulation.spawn_manual(ThreatType.MISSILE, float(x))
                elif event.button == 3:
                    simulation.spawn_manual(ThreatType.DRONE, float(x))

        simulation.update(dt)
        renderer.draw(screen, simulation)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
