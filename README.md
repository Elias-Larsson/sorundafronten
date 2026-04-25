# Intelligent Air Defense Decision Support Prototype

This repository contains a 1-week prototype for a hybrid air defense decision support system.

Core design principle:

- AI module provides threat analysis only (structured JSON)
- deterministic decision algorithm makes all final tactical actions

## What the prototype demonstrates

- real-time aerial threat simulation (missiles and drones)
- continuous prioritization using AI analysis inputs
- deterministic response selection under resource constraints
- forward-looking preservation behavior (reserves, cooldowns, availability)
- visual explanation of decisions and AI outputs in the UI

## Project structure

```
ai/
	analyzer.py            # AI analysis only (threat_level, urgency, likely_target, confidence)
core/
	decision_engine.py     # Deterministic rule-based final decision logic
	simulation.py          # Simulation state, spawning, updates, engagements
	renderer.py            # Pygame drawing and HUD
models/
	threat.py              # Threat objects
	resource.py            # Ammo/readiness/cooldown/recovery
	asset.py               # Defended assets
	interceptor.py         # Interceptor objects
main.py                  # Pygame application loop
```

## Run

1. Create and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

3. Start simulation:

```bash
python main.py
```

## Controls

- `M`: spawn missile
- `D`: spawn drone
- `W`: spawn random wave
- left click: spawn missile at cursor x-position
- right click: spawn drone at cursor x-position
- `ESC`: quit

## Hybrid architecture constraints in this implementation

- AI never issues actions and never controls resources.
- AI output is structured and visible as JSON in the HUD.
- Decision engine is deterministic, explainable, and rule-based.
- Resource use accounts for:
  - ammo limits
  - launch cooldowns
  - unit readiness and delayed recovery
  - reserve preservation for future threats
