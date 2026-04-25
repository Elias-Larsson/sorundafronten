from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

import pygame


@dataclass(frozen=True)
class MapLocation:
    feature_name: str
    side: str
    subtype: str
    x_km: float
    y_km: float
    notes: str


@dataclass(frozen=True)
class MapTerrain:
    feature_id: str
    side: str
    subtype: str
    points_km: list[tuple[float, float]]


@dataclass(frozen=True)
class MapData:
    csv_path: Path
    svg_path: Path
    world_width_km: float
    world_height_km: float
    svg_view_width: float
    svg_view_height: float
    locations: list[MapLocation]
    terrains: list[MapTerrain]


class MapProjector:
    def __init__(
        self,
        world_width_km: float,
        world_height_km: float,
        screen_width: int,
        screen_height: int,
        padding: int = 0,
    ):
        self.world_width_km = max(1.0, world_width_km)
        self.world_height_km = max(1.0, world_height_km)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.padding = max(0, padding)

        available_width = max(1.0, float(screen_width - 2 * self.padding))
        available_height = max(1.0, float(screen_height - 2 * self.padding))
        self.scale = min(available_width / self.world_width_km, available_height / self.world_height_km)

        self.pixel_width = self.world_width_km * self.scale
        self.pixel_height = self.world_height_km * self.scale

        self.offset_x = (screen_width - self.pixel_width) / 2.0
        self.offset_y = (screen_height - self.pixel_height) / 2.0

    def to_screen(self, x_km: float, y_km: float) -> tuple[float, float]:
        return (
            self.offset_x + x_km * self.scale,
            self.offset_y + y_km * self.scale,
        )

    def polygon_to_screen(self, points_km: Iterable[tuple[float, float]]) -> list[tuple[int, int]]:
        projected = []
        for x_km, y_km in points_km:
            x_px, y_px = self.to_screen(x_km, y_km)
            projected.append((int(round(x_px)), int(round(y_px))))
        return projected


def load_map_data(csv_path: str | Path, svg_path: str | Path) -> MapData:
    csv_file = Path(csv_path)
    svg_file = Path(svg_path)

    locations: list[MapLocation] = []
    terrains: list[MapTerrain] = []

    max_x = 0.0
    max_y = 0.0

    with csv_file.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            record_type = (row.get("record_type") or "").strip().lower()
            if record_type == "location":
                x_km = _to_float(row.get("x_km"), 0.0)
                y_km = _to_float(row.get("y_km"), 0.0)
                max_x = max(max_x, x_km)
                max_y = max(max_y, y_km)

                locations.append(
                    MapLocation(
                        feature_name=(row.get("feature_name") or "").strip(),
                        side=(row.get("side") or "").strip().lower(),
                        subtype=(row.get("subtype") or "").strip().lower(),
                        x_km=x_km,
                        y_km=y_km,
                        notes=(row.get("notes") or "").strip(),
                    )
                )

            elif record_type == "terrain":
                points_km: list[tuple[float, float]] = []
                points_raw = (row.get("coordinates_km") or "").strip()
                if points_raw:
                    try:
                        parsed = json.loads(points_raw)
                        for point in parsed:
                            x_km = float(point[0])
                            y_km = float(point[1])
                            points_km.append((x_km, y_km))
                            max_x = max(max_x, x_km)
                            max_y = max(max_y, y_km)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        points_km = []

                terrains.append(
                    MapTerrain(
                        feature_id=(row.get("feature_id") or "").strip(),
                        side=(row.get("side") or "").strip().lower(),
                        subtype=(row.get("subtype") or "").strip().lower(),
                        points_km=points_km,
                    )
                )

    svg_view_width, svg_view_height = _read_svg_viewbox(svg_file)

    world_width_km = max(1666.7, max_x)
    world_height_km = max(1300.0, max_y)

    if svg_view_width > 0 and svg_view_height > 0:
        svg_ratio = svg_view_width / svg_view_height
        csv_ratio = world_width_km / max(1.0, world_height_km)
        if abs(svg_ratio - csv_ratio) > 0.03:
            world_height_km = world_width_km / svg_ratio

    return MapData(
        csv_path=csv_file,
        svg_path=svg_file,
        world_width_km=world_width_km,
        world_height_km=world_height_km,
        svg_view_width=svg_view_width,
        svg_view_height=svg_view_height,
        locations=locations,
        terrains=terrains,
    )


def load_svg_background(svg_path: str | Path, projector: MapProjector) -> pygame.Surface | None:
    svg_file = Path(svg_path)
    if not svg_file.exists():
        return None

    try:
        text = svg_file.read_text(encoding="utf-8")
        root = ET.fromstring(text)
        view_width, view_height = _read_viewbox_from_root(root)
        if view_width <= 0:
            view_width = projector.world_width_km
        if view_height <= 0:
            view_height = projector.world_height_km

        # Normalize width/height to concrete numeric values so SDL_image loads the SVG reliably.
        normalized_svg = _normalize_svg_size(text, view_width, view_height)

        raw_surface = pygame.image.load(io.BytesIO(normalized_svg.encode("utf-8")), "map.svg")
        if projector.pixel_width < 1 or projector.pixel_height < 1:
            return _safe_convert_alpha(raw_surface)

        target_size = (
            max(1, int(round(projector.pixel_width))),
            max(1, int(round(projector.pixel_height))),
        )
        scaled = pygame.transform.smoothscale(raw_surface, target_size)
        return _safe_convert_alpha(scaled)
    except (OSError, ET.ParseError, pygame.error):
        return None


def _read_svg_viewbox(svg_file: Path) -> tuple[float, float]:
    if not svg_file.exists():
        return 0.0, 0.0

    try:
        root = ET.fromstring(svg_file.read_text(encoding="utf-8"))
        return _read_viewbox_from_root(root)
    except (OSError, ET.ParseError):
        return 0.0, 0.0


def _read_viewbox_from_root(root: ET.Element) -> tuple[float, float]:
    view_box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(view_box) != 4:
        return 0.0, 0.0

    return _to_float(view_box[2], 0.0), _to_float(view_box[3], 0.0)


def _to_float(value: str | None, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_svg_size(svg_text: str, width: float, height: float) -> str:
    width_value = f'width="{width:.1f}"'
    height_value = f'height="{height:.1f}"'

    normalized = svg_text

    if re.search(r'\bwidth\s*=\s*"[^"]*"', normalized):
        normalized = re.sub(
            r'\bwidth\s*=\s*"[^"]*"',
            width_value,
            normalized,
            count=1,
        )
    else:
        normalized = normalized.replace("<svg", f"<svg {width_value}", 1)

    if re.search(r'\bheight\s*=\s*"[^"]*"', normalized):
        normalized = re.sub(
            r'\bheight\s*=\s*"[^"]*"',
            height_value,
            normalized,
            count=1,
        )
    else:
        normalized = normalized.replace("<svg", f"<svg {height_value}", 1)

    return normalized


def _safe_convert_alpha(surface: pygame.Surface) -> pygame.Surface:
    try:
        return surface.convert_alpha()
    except pygame.error:
        return surface
