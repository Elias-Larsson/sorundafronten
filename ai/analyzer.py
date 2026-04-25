from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import threading
import time
from typing import Iterable, Sequence
import urllib.request

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
    If GEMINI_API is present, analysis is refreshed asynchronously from Gemini/OpenRouter;
    otherwise it uses local heuristic analysis only.
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API", "").strip()
        self.backend = self._select_backend(self.api_key)
        self.provider_status = self._initial_provider_status()

        self._gemini_model = "gemini-2.0-flash"
        self._openrouter_model = "google/gemini-2.0-flash-001"

        self._request_interval_seconds = 4.0
        self._cache_ttl_seconds = 18.0
        self._retry_backoff_seconds = 12.0

        self._next_refresh_at = 0.0
        self._next_retry_at = 0.0
        self._request_thread: threading.Thread | None = None

        self._cache: dict[int, tuple[ThreatAnalysis, float]] = {}
        self._lock = threading.Lock()

    def analyze(self, threat: Threat, assets: Iterable[Asset]) -> ThreatAnalysis:
        return self._heuristic_analysis(threat, assets)

    def analyze_all(
        self,
        threats: Sequence[Threat],
        assets: Sequence[Asset],
    ) -> dict[int, ThreatAnalysis]:
        alive_threats = [threat for threat in threats if threat.alive]
        if not alive_threats:
            return {}

        heuristic = {
            threat.threat_id: self._heuristic_analysis(threat, assets) for threat in alive_threats
        }

        if self.backend == "disabled":
            self.provider_status = "heuristic-only (no GEMINI_API)"
            return heuristic

        self._start_refresh_if_due(alive_threats, assets, heuristic)
        return self._merge_with_cache(heuristic)

    def analyze_turn_blocking(
        self,
        threats: Sequence[Threat],
        assets: Sequence[Asset],
        timeout_seconds: float = 10.0,
    ) -> dict[int, ThreatAnalysis]:
        alive_threats = [threat for threat in threats if threat.alive]
        if not alive_threats:
            return {}

        heuristic = {
            threat.threat_id: self._heuristic_analysis(threat, assets) for threat in alive_threats
        }

        if self.backend == "disabled":
            self.provider_status = "heuristic-only (no GEMINI_API)"
            return heuristic

        threat_payload = [
            {
                "threat_id": threat.threat_id,
                "threat_type": threat.threat_type.value,
                "x": round(threat.x, 2),
                "y": round(threat.y, 2),
                "speed": round(threat.speed, 2),
                "intended_target_id": threat.intended_target_id,
            }
            for threat in sorted(
                alive_threats,
                key=lambda item: heuristic[item.threat_id].urgency,
                reverse=True,
            )[:12]
        ]

        asset_payload = [
            {
                "asset_id": asset.asset_id,
                "kind": asset.kind,
                "x": round(asset.x, 2),
                "y": round(asset.y, 2),
                "strategic_value": round(asset.strategic_value, 3),
                "alive": bool(asset.is_alive()),
            }
            for asset in assets
            if asset.is_alive()
        ]

        baseline_payload = {
            threat_id: analysis.to_json() for threat_id, analysis in heuristic.items()
        }

        with self._lock:
            self.provider_status = f"{self.backend}:waiting-response"

        try:
            prompt = self._build_prompt(threat_payload, asset_payload, baseline_payload)
            response_text = self._query_backend(prompt, timeout_seconds=timeout_seconds)

            valid_asset_ids = {asset["asset_id"] for asset in asset_payload}
            parsed = self._parse_response(response_text, baseline_payload, valid_asset_ids)

            merged = dict(heuristic)
            merged.update(parsed)

            now = time.monotonic()
            with self._lock:
                for threat_id, analysis in merged.items():
                    self._cache[threat_id] = (analysis, now)

                self.provider_status = f"{self.backend}:turn-ready"
                self._next_retry_at = 0.0

            return merged
        except Exception as exc:
            with self._lock:
                self.provider_status = f"{self.backend}:turn-fallback ({type(exc).__name__})"
                self._next_retry_at = time.monotonic() + self._retry_backoff_seconds

            return heuristic

    def _heuristic_analysis(self, threat: Threat, assets: Iterable[Asset]) -> ThreatAnalysis:
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

    def _start_refresh_if_due(
        self,
        threats: Sequence[Threat],
        assets: Sequence[Asset],
        heuristic: dict[int, ThreatAnalysis],
    ) -> None:
        now = time.monotonic()
        with self._lock:
            if self._request_thread is not None and self._request_thread.is_alive():
                return

            if now < self._next_refresh_at or now < self._next_retry_at:
                return

            self._next_refresh_at = now + self._request_interval_seconds

            threat_payload = [
                {
                    "threat_id": threat.threat_id,
                    "threat_type": threat.threat_type.value,
                    "x": round(threat.x, 2),
                    "y": round(threat.y, 2),
                    "speed": round(threat.speed, 2),
                    "intended_target_id": threat.intended_target_id,
                }
                for threat in sorted(
                    threats,
                    key=lambda item: heuristic[item.threat_id].urgency,
                    reverse=True,
                )[:8]
            ]

            asset_payload = [
                {
                    "asset_id": asset.asset_id,
                    "kind": asset.kind,
                    "x": round(asset.x, 2),
                    "y": round(asset.y, 2),
                    "strategic_value": round(asset.strategic_value, 3),
                    "alive": bool(asset.is_alive()),
                }
                for asset in assets
                if asset.is_alive()
            ]

            baseline_payload = {
                threat_id: analysis.to_json() for threat_id, analysis in heuristic.items()
            }

            self.provider_status = f"{self.backend}:requesting"
            self._request_thread = threading.Thread(
                target=self._refresh_worker,
                args=(threat_payload, asset_payload, baseline_payload),
                daemon=True,
            )
            self._request_thread.start()

    def _refresh_worker(
        self,
        threat_payload: list[dict[str, int | float | str]],
        asset_payload: list[dict[str, int | float | str | bool]],
        baseline_payload: dict[int, dict[str, int | float | str]],
    ) -> None:
        try:
            prompt = self._build_prompt(threat_payload, asset_payload, baseline_payload)
            response_text = self._query_backend(prompt)

            valid_asset_ids = {asset["asset_id"] for asset in asset_payload}
            parsed = self._parse_response(response_text, baseline_payload, valid_asset_ids)

            now = time.monotonic()
            with self._lock:
                for threat_id, analysis in parsed.items():
                    self._cache[threat_id] = (analysis, now)

                self.provider_status = f"{self.backend}:live"
                self._next_retry_at = 0.0
        except Exception as exc:
            with self._lock:
                self.provider_status = f"{self.backend}:fallback ({type(exc).__name__})"
                self._next_retry_at = time.monotonic() + self._retry_backoff_seconds
        finally:
            with self._lock:
                self._request_thread = None

    def _build_prompt(
        self,
        threat_payload: list[dict[str, int | float | str]],
        asset_payload: list[dict[str, int | float | str | bool]],
        baseline_payload: dict[int, dict[str, int | float | str]],
    ) -> str:
        payload = {
            "task": (
                "Provide threat analysis only. Do not make response decisions. "
                "Output JSON only."
            ),
            "required_fields": [
                "threat_id",
                "threat_level",
                "urgency",
                "likely_target",
                "confidence",
            ],
            "constraints": {
                "threat_level": "0..1",
                "urgency": "0..1",
                "confidence": "0..1",
                "likely_target": "must be one of asset_id values",
            },
            "baseline_analysis": baseline_payload,
            "assets": asset_payload,
            "threats": threat_payload,
            "output_schema": {
                "analyses": [
                    {
                        "threat_id": 1,
                        "threat_level": 0.0,
                        "urgency": 0.0,
                        "likely_target": "asset_id",
                        "confidence": 0.0,
                    }
                ]
            },
        }
        return json.dumps(payload, separators=(",", ":"))

    def _query_backend(self, prompt: str, timeout_seconds: float = 6.0) -> str:
        if self.backend == "openrouter":
            return self._query_openrouter(prompt, timeout_seconds)
        if self.backend == "gemini-rest":
            return self._query_gemini_rest(prompt, timeout_seconds)
        raise RuntimeError("No remote backend configured")

    def _query_openrouter(self, prompt: str, timeout_seconds: float = 6.0) -> str:
        body = {
            "model": self._openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON analysis service for air defense. "
                        "Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.0,
            "max_tokens": 700,
        }

        request = urllib.request.Request(
            url="https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/Elias-Larsson/sorundafronten",
                "X-Title": "sorundafronten-prototype",
            },
        )

        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter returned no choices")

        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned empty content")

        return content

    def _query_gemini_rest(self, prompt: str, timeout_seconds: float = 6.0) -> str:
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "topP": 0.9,
            },
        }

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._gemini_model}:generateContent?key={self.api_key}"
        )

        request = urllib.request.Request(
            url=endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini REST returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Gemini REST returned no text parts")

        text = parts[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Gemini REST returned empty text")

        return text

    def _parse_response(
        self,
        response_text: str,
        baseline_payload: dict[int, dict[str, int | float | str]],
        valid_asset_ids: set[str],
    ) -> dict[int, ThreatAnalysis]:
        parsed = self._extract_json(response_text)

        if isinstance(parsed, dict):
            items = parsed.get("analyses")
            if not isinstance(items, list):
                items = []
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = []

        output: dict[int, ThreatAnalysis] = {}

        for item in items:
            if not isinstance(item, dict):
                continue

            threat_id = self._safe_int(item.get("threat_id"))
            if threat_id is None or threat_id not in baseline_payload:
                continue

            baseline = baseline_payload[threat_id]
            default_target = str(baseline.get("likely_target", "none"))

            likely_target = str(item.get("likely_target", default_target))
            if likely_target not in valid_asset_ids:
                likely_target = default_target

            output[threat_id] = ThreatAnalysis(
                threat_id=threat_id,
                threat_level=_clamp(
                    self._safe_float(item.get("threat_level"), float(baseline.get("threat_level", 0.0)))
                ),
                urgency=_clamp(self._safe_float(item.get("urgency"), float(baseline.get("urgency", 0.0)))),
                likely_target=likely_target,
                confidence=_clamp(
                    self._safe_float(item.get("confidence"), float(baseline.get("confidence", 0.0)))
                ),
            )

        return output

    def _merge_with_cache(
        self,
        heuristic: dict[int, ThreatAnalysis],
    ) -> dict[int, ThreatAnalysis]:
        now = time.monotonic()

        with self._lock:
            stale_ids = [
                threat_id
                for threat_id, (_, ts) in self._cache.items()
                if now - ts > self._cache_ttl_seconds
            ]
            for threat_id in stale_ids:
                del self._cache[threat_id]

            cached = {threat_id: pair[0] for threat_id, pair in self._cache.items()}

        merged = dict(heuristic)
        for threat_id, cached_analysis in cached.items():
            if threat_id in merged:
                merged[threat_id] = cached_analysis
        return merged

    def _select_backend(self, api_key: str) -> str:
        if not api_key:
            return "disabled"
        if api_key.startswith("sk-or-v1-"):
            return "openrouter"
        return "gemini-rest"

    def _initial_provider_status(self) -> str:
        if self.backend == "disabled":
            return "heuristic-only (no GEMINI_API)"
        return f"{self.backend}:idle"

    def _extract_json(self, text: str) -> dict | list:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start_obj = cleaned.find("{")
        end_obj = cleaned.rfind("}")
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            try:
                return json.loads(cleaned[start_obj : end_obj + 1])
            except json.JSONDecodeError:
                pass

        start_arr = cleaned.find("[")
        end_arr = cleaned.rfind("]")
        if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
            return json.loads(cleaned[start_arr : end_arr + 1])

        raise json.JSONDecodeError("No JSON payload found", cleaned, 0)

    def _safe_float(self, value: object, default: float) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _safe_int(self, value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
