import csv
import math
import random



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
                base = {
                    "name": row["feature_name"],
                    "x": float(row["x_km"]),
                    "y": float(row["y_km"]),
                    "capacity": 2,
                    "speed": 1.0,
                    "range": 500,
                    "capabilities": random.choice(capability_options)
                }

                bases.append(base)

    return bases


def create_threats():
    threats = [
        {"id": 1, "x": 500, "y": 200, "type": "missile", "priority": 10},
        {"id": 2, "x": 100, "y": 800, "type": "drone", "priority": 5},
        {"id": 3, "x": 300, "y": 400, "type": "aircraft", "priority": 8},
    ]
    return threats


def distance(a, b):
    return math.sqrt((a["x"] - b["x"])**2 + (a["y"] - b["y"])**2)

def cost(base, threat):
    d = distance(base, threat)

    # kan inte nå
    if d > base["range"]:
        return float("inf")

    distance_weight = 1.0
    priority_weight = 100.0

    score = (d * distance_weight) - (threat["priority"] * priority_weight)

    # penalty om dålig matchning
    if threat["type"] not in base["capabilities"]:
        score += 1000

    return score


def assign_bases_to_threats(bases, threats):
    assignments = []
    unassigned = []

    for threat in threats:
        best_base = None
        best_score = float("inf")

        for base in bases:
            if base["capacity"] > 0:
                score = cost(base, threat)

                if score < best_score:
                    best_score = score
                    best_base = base

        if best_base:
            assignments.append((best_base, threat))
            best_base["capacity"] -= 1
        else:
            unassigned.append(threat)

    return assignments, unassigned


def main():
    bases = load_bases("Boreal_passage_coordinates.csv")
    threats = create_threats()

    threats = sorted(threats, key=lambda t: t["priority"], reverse=True)

    assignments, unassigned = assign_bases_to_threats(bases, threats)

    print("\nAssignments:")
    for base, threat in assignments:
        print(f"{base['name']} -> Threat {threat['id']}")

    print("\nUnassigned threats:")
    for t in unassigned:
        print(f"Threat {t['id']}")
    
    print("Number of bases:", len(bases))



if __name__ == "__main__":
    main()