from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from models import Asset, Threat, ThreatType


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


@dataclass
class ThreatAnalysis:
    threat_id: int
    threat_level: float
    urgency: float
    likely_target: str
    confidence: float

    def to_json(self) -> dict[str, float | str | int]:
        return {
            "threat_id": self.threat_id,
            "threat_level": round(self.threat_level, 3),
            "urgency": round(self.urgency, 3),
            "likely_target": self.likely_target,
            "confidence": round(self.confidence, 3),
        }


class ThreatAnalyzer:
    """AI-only analysis component.

    This module provides structured threat analysis and never decides responses.
    """

    def analyze(self, threat: Threat, assets: Iterable[Asset]) -> ThreatAnalysis:
        alive_assets = [asset for asset in assets if asset.is_alive()]
        if not alive_assets:
            return ThreatAnalysis(
                threat_id=threat.threat_id,
                threat_level=0.0,
                urgency=0.0,
                likely_target="none",
                confidence=0.0,
            )

        nearest_asset = min(alive_assets, key=lambda asset: threat.distance_to(asset.x, asset.y))
        intended_asset = next(
            (asset for asset in alive_assets if asset.asset_id == threat.intended_target_id),
            nearest_asset,
        )

        intended_distance = threat.distance_to(intended_asset.x, intended_asset.y)
        nearest_distance = threat.distance_to(nearest_asset.x, nearest_asset.y)
        likely_target_asset = intended_asset if intended_distance <= nearest_distance + 120 else nearest_asset

        type_risk = 0.90 if threat.threat_type == ThreatType.MISSILE else 0.45
        speed_factor = _clamp(threat.speed / 220.0)
        distance_factor = 1.0 - _clamp(
            threat.distance_to(likely_target_asset.x, likely_target_asset.y) / 900.0
        )
        value_factor = _clamp(likely_target_asset.strategic_value)

        threat_level = _clamp(
            0.45 * type_risk + 0.20 * speed_factor + 0.20 * distance_factor + 0.15 * value_factor
        )

        eta_seconds = threat.eta_seconds(likely_target_asset.x, likely_target_asset.y)
        urgency = _clamp(1.0 - min(1.0, eta_seconds / 12.0))

        if likely_target_asset.asset_id == threat.intended_target_id:
            confidence = 0.88 - 0.20 * _clamp(intended_distance / 1200.0)
        else:
            confidence = 0.70 - 0.15 * _clamp(nearest_distance / 1200.0)

        confidence = _clamp(confidence, 0.35, 0.95)

        return ThreatAnalysis(
            threat_id=threat.threat_id,
            threat_level=threat_level,
            urgency=urgency,
            likely_target=likely_target_asset.asset_id,
            confidence=confidence,
        )
