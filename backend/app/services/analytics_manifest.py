from __future__ import annotations

import hashlib
import json
from typing import Any


DEMO_MODEL_REGISTRY: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("risk", "deterministic-demo-v0.1", {"purpose": "risk decision-support"}),
    ("scenario", "deterministic-demo-v0.1", {"purpose": "scenario decision-support"}),
)

DEMO_RULESET_REGISTRY: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("feature", "intake-feature-set-v0.1-demo", {"sections": ["profile", "financials", "products", "evidence"]}),
    ("risk", "intake-risk-rules-v0.1", {"inputs": ["cashflow", "debt", "late_payment", "delivery_delay"]}),
    ("matching", "supplier-shortlist-rules-v0.1", {"guardrail": "consent_required"}),
    ("scenario", "scenario-rules-v0.1", {"guardrail": "human_review_required"}),
)


def registry_config_json(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, sort_keys=True)


def registry_checksum(artifact_type: str, version: str, config: dict[str, Any]) -> str:
    payload = f"{artifact_type}:{version}:{registry_config_json(config)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
