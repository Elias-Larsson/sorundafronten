
# Sorundafronten

**An experimental 2D airbase engagement simulation built with Python and Pygame.**

Sorundafronten is a small simulation prototype exploring moving entities, automated target selection, projectile interception, and simple combat logic on a map loaded from CSV data. The project was created as a programming experiment rather than a finished game or a real-world defense system. This project was for a hackathon competition at KTH with saab.

## What It Does

The current Pygame prototype includes:

- **Map rendering:** Terrain polygons and airbase positions loaded from a CSV file.
- **Aircraft movement:** Aircraft move toward a selected opposing base.
- **Automated targeting:** Bases select the nearest eligible opposing aircraft and launch missiles after a cooldown.
- **Missile movement:** Missiles travel toward targets and can acquire a new target if the original one disappears.
- **Collision handling:** Aircraft can damage opposing bases, and missiles can intercept aircraft.
- **Interactive spawning:** Clicking inside the simulation spawns an aircraft on the north side, targeting the nearest south-side base.
- **Real-time visualization:** A Pygame window updates the simulation at up to 60 FPS.

The target selection is rule-based and distance-based; it does not use machine learning.

## Tech Stack

- **Python** — simulation logic
- **Pygame** — rendering, input, and frame updates
- **CSV and JSON** — terrain and location data
- **FastAPI** — a separate, minimal API scaffold

## Repository Structure

```text
sorundafronten/
├── backend/
│   ├── game.py       # Pygame simulation
│   └── main.py       # Minimal FastAPI application
├── .gitignore
├── LICENSE           # MIT
└── README.md
```

## Running the Simulation

### Requirements

- Python 3
- `pygame`
- A `map.csv` file (see below)

### 1. Clone the repository

```bash
git clone https://github.com/Elias-Larsson/sorundafronten.git
cd sorundafronten
```

### 2. Create a virtual environment

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Pygame

```bash
python -m pip install pygame
```

### 4. Provide map data

`backend/game.py` reads a file named `map.csv` from the **current working directory**. That file is not included in the repository at present.

To try the prototype, create `backend/map.csv` with the following example data:

```csv
record_type,subtype,x_km,y_km,side,coordinates_km
location,air_base,350,350,north,
location,air_base,1300,950,south,
terrain,,,,north,"[[70,70],[750,70],[750,570],[70,570]]"
terrain,,,,south,"[[930,710],[1580,710],[1580,1250],[930,1250]]"
```

The `record_type` field must be `location` or `terrain`:

- A location with `subtype=air_base` creates a base from `x_km`, `y_km`, and `side`.
- A terrain row uses `coordinates_km` as a JSON-encoded list of polygon points.
- The recognized sides are `north` and `south`.

The map is scaled from an internal coordinate space of approximately 1666.7 × 1300 into the 1000 × 800 Pygame window.

### 5. Start the simulation

From the repository root:

```bash
cd backend
python game.py
```

Click on the map to spawn a north-side aircraft. The aircraft moves toward the closest south-side base; opposing bases fire missiles when targets are available. Close the window to exit.

> **Note:** This prototype assumes the CSV data exists and follows the expected format. It currently has no configuration interface or built-in map editor.

## FastAPI Scaffold

The repository also contains a separate FastAPI application in `backend/main.py`. **It is not connected to the Pygame simulation yet.** Currently, it provides only a test endpoint that returns `{"message": "Hello World"}`.

To run it, install the dependencies:

```bash
python -m pip install fastapi uvicorn
```

From the `backend/` directory:

```bash
uvicorn main:app --reload
```

Then visit:

- **API:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Interactive API documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Current Limitations

Sorundafronten is an early prototype, with several limitations:

- The repository does not yet ship with `map.csv` or a dependency manifest such as `requirements.txt`.
- Only north-side aircraft can currently be spawned by mouse input.
- Target selection uses simple nearest-target rules.
- There is no start menu, victory/defeat state, save system, or polished user interface.
- The FastAPI scaffold does not control or expose simulation state.
- The simulation is intended for experimentation, not operational decision-making.

## Potential Next Steps

Ideas for future iterations (not implemented):

- Store example maps in the repository and add map validation.
- Separate simulation state and rendering for easier automated testing.
- Add configurable scenarios, aircraft types, and interception rules.
- Implement a user interface for simulation controls and statistics.
- Expose simulation state through a documented API.

## License

Distributed under the [MIT License](LICENSE).

## Author

Developed by **Elias Larsson**.

- [Portfolio](https://eliaslarsson.dev)
- [GitHub](https://github.com/Elias-Larsson)
