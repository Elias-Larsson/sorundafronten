import csv
import math
import random

random.seed(42)

# -------------------------
# CONSTANTS
# -------------------------
BASE_SPEED = 5.0
BASE_RANGE = 1000

MAX_INTERCEPT_TIME = 1000
MAX_DISTANCE = 1e6

W_TIME = 10
W_PRIORITY = 30
W_MARGIN = 5

PENALTY_LATE = 500
PENALTY_CAPABILITY = 200


# -------------------------
# LOAD BASES
# -------------------------
def load_bases(filename):
    bases = []

    capability_options = [
        ["aircraft"],
        ["drone"],
        ["aircraft", "drone"],
        ["missile"]
    ]

    with open(filename, newline='') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            if row["subtype"] == "air_base":
                bases.append({
                    "name": row["feature_name"],
                    "x": float(row["x_km"]),
                    "y": float(row["y_km"]),
                    "speed": BASE_SPEED,
                    "range": BASE_RANGE,
                    "capabilities": random.choice(capability_options),
                    "schedule": []
                })

    return bases


# -------------------------
# THREATS
# -------------------------
def create_threats():
    return [
        {"id": 1, "x": 500, "y": 200, "type": "missile", "priority": 10, "speed": 5.0, "dx": -1, "dy": 0},
        {"id": 2, "x": 100, "y": 800, "type": "drone", "priority": 5, "speed": 1.0, "dx": 1, "dy": -1},
        {"id": 3, "x": 300, "y": 400, "type": "aircraft", "priority": 8, "speed": 3.0, "dx": 0, "dy": -1},
    ]


# -------------------------
# UTIL
# -------------------------
def normalize(dx, dy):
    length = math.hypot(dx, dy)
    if length == 0:
        return 0, 0
    return dx / length, dy / length


def future_position(threat, t):
    dx, dy = normalize(threat["dx"], threat["dy"])
    return (
        threat["x"] + dx * threat["speed"] * t,
        threat["y"] + dy * threat["speed"] * t
    )


# -------------------------
# MOVE THREATS
# -------------------------
def move_threats(threats, dt=1.0):
    print("\n--- MOVING THREATS ---")

    for t in threats:
        dx, dy = normalize(t["dx"], t["dy"])

        old_x, old_y = t["x"], t["y"]

        t["x"] += dx * t["speed"] * dt
        t["y"] += dy * t["speed"] * dt

        print(f"Threat {t['id']} moved ({old_x:.1f},{old_y:.1f}) -> ({t['x']:.1f},{t['y']:.1f})")


# -------------------------
# SCHEDULE
# -------------------------
def clean_schedule(base, current_time):
    base["schedule"] = [s for s in base["schedule"] if s[1] > current_time]


def get_available_time(schedule, current_time):
    if not schedule:
        return current_time
    return max(current_time, max(s[1] for s in schedule))


# -------------------------
# TIME TO IMPACT
# -------------------------
def threat_time_to_impact(threat, target=(0, 0)):
    dx, dy = normalize(threat["dx"], threat["dy"])

    vx = target[0] - threat["x"]
    vy = target[1] - threat["y"]

    dot = vx * dx + vy * dy

    if dot <= 0:
        return float("inf")

    return dot / threat["speed"]


# -------------------------
# INTERCEPT (SAFE)
# -------------------------
def intercept_time(base, threat, start_delay=0):
    bx, by = base["x"], base["y"]

    dx, dy = normalize(threat["dx"], threat["dy"])

    tx, ty = future_position(threat, start_delay)

    rx = tx - bx
    ry = ty - by

    # sanity check (avoid overflow)
    if abs(rx) > MAX_DISTANCE or abs(ry) > MAX_DISTANCE:
        return None

    vx = dx * threat["speed"]
    vy = dy * threat["speed"]
    s = base["speed"]

    a = vx**2 + vy**2 - s**2
    b = 2 * (rx * vx + ry * vy)
    c = rx**2 + ry**2

    # linear case
    if abs(a) < 1e-6:
        if abs(b) < 1e-6:
            return None
        t = -c / b
        return t if 0 < t < MAX_INTERCEPT_TIME else None

    # quadratic case (safe)
    try:
        disc = b*b - 4*a*c
    except OverflowError:
        return None

    if disc < 0:
        return None

    sqrt_disc = math.sqrt(disc)

    t1 = (-b - sqrt_disc) / (2*a)
    t2 = (-b + sqrt_disc) / (2*a)

    valid = [t for t in (t1, t2) if 0 < t < MAX_INTERCEPT_TIME]
    return min(valid) if valid else None


# -------------------------
# COST
# -------------------------
def cost(base, threat, total_time, start_delay):
    time_limit = threat_time_to_impact(threat) - start_delay
    if time_limit <= 0:
        return float("inf")

    tx, ty = future_position(threat, total_time)
    d = math.hypot(base["x"] - tx, base["y"] - ty)

    margin = max(0, time_limit - total_time)

    score = (
        total_time * W_TIME
        - threat["priority"] * W_PRIORITY
        - margin * W_MARGIN
    )

    if total_time > time_limit:
        score += PENALTY_LATE

    if threat["type"] not in base["capabilities"]:
        score += PENALTY_CAPABILITY

    if d > base["range"]:
        score += (d - base["range"]) * 2

    return score


# -------------------------
# ASSIGNMENT
# -------------------------
def assign_bases_to_threats(bases, threats, current_time):
    print(f"\n===== ASSIGNMENT STEP t={current_time} =====")

    for base in bases:
        clean_schedule(base, current_time)

    for threat in threats:

        # skip irrelevant threats
        if threat_time_to_impact(threat) <= 0:
            continue

        best = None
        best_score = float("inf")

        for base in bases:
            start_time = get_available_time(base["schedule"], current_time)
            start_delay = start_time - current_time

            t_int = intercept_time(base, threat, start_delay)
            if t_int is None:
                continue

            total_time = start_delay + t_int
            score = cost(base, threat, total_time, start_delay)

            if score < best_score:
                best_score = score
                best = (base, t_int, start_time)

        if best:
            base, t_int, start_time = best
            end_time = start_time + t_int

            # remove old assignment
            if "assigned_base" in threat:
                old_base = threat["assigned_base"]
                old_base["schedule"] = [
                    s for s in old_base["schedule"] if s[2] != threat["id"]
                ]

            base["schedule"].append((start_time, end_time, threat["id"]))

            threat["assigned_base"] = base
            threat["intercept_time"] = end_time

            print(f"✔ {base['name']} -> Threat {threat['id']} (t={end_time:.1f})")


# -------------------------
# CLEANUP
# -------------------------
def remove_finished_threats(threats, current_time):
    remaining = []

    print("\n--- CLEANUP ---")

    for t in threats:
        if "intercept_time" in t and current_time >= t["intercept_time"]:
            print(f"✔ Threat {t['id']} INTERCEPTED")
        elif threat_time_to_impact(t) == float("inf"):
            print(f"✈️ Threat {t['id']} ESCAPED")
        elif abs(t["x"]) < 50 and abs(t["y"]) < 50:
            print(f"💥 Threat {t['id']} HIT TARGET")
        else:
            remaining.append(t)

    return remaining


# -------------------------
# MAIN
# -------------------------
def main():
    bases = load_bases("Boreal_passage_coordinates.csv")
    threats = create_threats()

    current_time = 0

    while threats:
        print("\n" + "="*40)
        print(f"TIME STEP {current_time}")
        print("="*40)

        threats = sorted(threats, key=lambda t: t["priority"], reverse=True)

        assign_bases_to_threats(bases, threats, current_time)

        move_threats(threats)

        threats = remove_finished_threats(threats, current_time)

        current_time += 1

    print("\n🎯 ALL THREATS RESOLVED")


if __name__ == "__main__":
    main()
    