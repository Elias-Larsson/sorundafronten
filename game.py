import pygame
import math
import csv
import json

pygame.init()

WIDTH, HEIGHT = 1000, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

# --- Map scaling ---
MAP_WIDTH = 1666.7
MAP_HEIGHT = 1300

def scale(x, y):
    sx = x / MAP_WIDTH * WIDTH
    sy = y / MAP_HEIGHT * HEIGHT
    return sx, sy

# --- Classes ---
class Plane:
    def __init__(self, x, y, target, side):
        self.x = x
        self.y = y
        self.target = target
        self.side = side
        self.speed = 3

    def update(self):
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.hypot(dx, dy)

        if dist > 0:
            self.x += dx / dist * self.speed
            self.y += dy / dist * self.speed

    def draw(self):
        color = (0, 200, 255) if self.side == "north" else (255, 120, 80)
        pygame.draw.circle(screen, color, (int(self.x), int(self.y)), 5)


class Missile:
    def __init__(self, x, y, target):
        self.x = x
        self.y = y
        self.target = target
        self.speed = 4

    def find_new_target(self, planes):
        if not planes:
            return None
        return min(planes, key=lambda p: math.hypot(p.x - self.x, p.y - self.y))

    def update(self):
        if self.target is None:
            return

        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.hypot(dx, dy)

        if dist > 0:
            self.x += dx / dist * self.speed
            self.y += dy / dist * self.speed

    def draw(self):
        pygame.draw.circle(screen, (255, 50, 50), (int(self.x), int(self.y)), 4)


class Base:
    def __init__(self, x, y, side):
        self.x = x
        self.y = y
        self.side = side
        self.hp = 50
        self.cooldown = 0

    def update(self, planes, missiles, targeted_planes):
        self.cooldown += 1

        if self.cooldown > 40:
            # attackera bara fiender
            enemy_planes = [p for p in planes if p.side != self.side and p not in targeted_planes]

            if enemy_planes:
                target = min(enemy_planes, key=lambda p: math.hypot(p.x - self.x, p.y - self.y))
                missiles.append(Missile(self.x, self.y, target))
                targeted_planes.add(target)
                self.cooldown = 0

    def draw(self):
        color = (100, 255, 100) if self.side == "north" else (255, 150, 100)
        pygame.draw.circle(screen, color, (int(self.x), int(self.y)), 10)


# --- Load CSV ---
locations = []
terrains = []

with open("map.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["record_type"] == "location":
            locations.append(row)
        elif row["record_type"] == "terrain":
            terrains.append(row)

# --- Create bases ---
bases = []
for loc in locations:
    if loc["subtype"] == "air_base":
        x = float(loc["x_km"])
        y = float(loc["y_km"])
        sx, sy = scale(x, y)

        bases.append(Base(sx, sy, loc["side"]))

planes = []
missiles = []

# --- Main loop ---
running = True
while running:
    clock.tick(60)

    # --- Draw ocean ---
    screen.fill((20, 40, 80))

    # --- Draw terrain ---
    for terrain in terrains:
        coords = json.loads(terrain["coordinates_km"])
        points = [scale(x, y) for x, y in coords]

        if terrain["side"] == "north":
            color = (50, 100, 50)
        else:
            color = (120, 90, 50)

        pygame.draw.polygon(screen, color, points)

    # --- Events ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = pygame.mouse.get_pos()

            # spawn north planes
            enemy_bases = [b for b in bases if b.side == "south"]
            if enemy_bases:
                target = min(enemy_bases, key=lambda b: math.hypot(mx - b.x, my - b.y))
                planes.append(Plane(mx, my, target, "north"))

    # --- AI targeting ---
    targeted_planes = set()

    # --- Update bases ---
    for base in bases:
        base.update(planes, missiles, targeted_planes)

    # --- Update planes ---
    for plane in planes[:]:
        plane.update()

        for base in bases:
            if base.side != plane.side:
                if math.hypot(plane.x - base.x, plane.y - base.y) < 12:
                    base.hp -= 10
                    planes.remove(plane)

                    if base.hp <= 0:
                        bases.remove(base)
                    break

    # --- Update missiles ---
    for missile in missiles[:]:

        if missile.target not in planes:
            missile.target = missile.find_new_target(planes)

            if missile.target is None:
                missiles.remove(missile)
                continue

        missile.update()

        for plane in planes[:]:
            if math.hypot(missile.x - plane.x, missile.y - plane.y) < 8:
                if plane in planes:
                    planes.remove(plane)
                if missile in missiles:
                    missiles.remove(missile)
                break

    # --- Draw entities ---
    for base in bases:
        base.draw()

    for plane in planes:
        plane.draw()

    for missile in missiles:
        missile.draw()

    pygame.display.flip()

pygame.quit()
