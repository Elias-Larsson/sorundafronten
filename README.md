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
	map_loader.py          # map.csv/map.svg loading and coordinate projection
models/
	threat.py              # Threat objects
	resource.py            # Ammo/readiness/cooldown/recovery
	asset.py               # Defended assets
	interceptor.py         # Interceptor objects
main.py                  # Pygame application loop
map.csv                  # Canonical terrain and location coordinates
map.svg                  # Visual map source + viewBox coordinate frame
```

## Run

 `LEFT` / `RIGHT` (or `Q` / `E`): switch highlighted target base
 left-click / right-click on a base: select highlighted target base
 `M`: queue missile against highlighted base
 `D`: queue drone against highlighted base

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Gemini API setup (`.env`)

The app now loads `.env` automatically at startup.

Create `.env` in the project root:

```bash
GEMINI_API=your_api_key_here
```

Supported key styles:

- Google Gemini REST API key
- OpenRouter key (`sk-or-v1-...`) targeting Gemini model

If `GEMINI_API` is missing or unreachable, the app falls back to local heuristic analysis.

## Controls

- `LEFT` / `RIGHT` (or `Q` / `E`): switch highlighted target base
- left-click / right-click on a base: select highlighted target base
- `M`: queue missile against highlighted base
- `D`: queue drone against highlighted base
- `C`: clear queued threats
- `ENTER` or `SPACE`: submit turn (send threats to Gemini, wait for response, then resolve)
- `ESC`: quit

## Turn flow

The simulation is now turn-based:

1. Player highlights one of the defender bases.
2. Player queues missiles and/or drones for that base.
3. Player can switch highlighted base and queue more threats to different bases in the same turn.
4. Player submits the turn.
5. System sends queued-threat context to Gemini analysis and waits for response.
6. Deterministic decision engine resolves engagements automatically.
7. When all threats/interceptors are resolved, control returns to player planning.

## Hybrid architecture constraints in this implementation

- AI never issues actions and never controls resources.
- AI output is structured and visible as JSON in the HUD.
- Decision engine is deterministic, explainable, and rule-based.
- `map.csv` provides operational coordinates for terrain, assets, and launch positions.
- `map.svg` is used as visual map background and coordinate calibration source.
- Resource use accounts for:
  - ammo limits
  - launch cooldowns
  - unit readiness and delayed recovery
  - reserve preservation for future threats
