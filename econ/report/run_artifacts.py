"""Helpers for reading persisted run artifacts (manifest, scenario files).

A run folder looks like ``runs/<id>/{simulation.db, manifest.json, scenario/}``;
these helpers resolve the scenario context next to a run's database path.
"""
from __future__ import annotations

import json
from pathlib import Path


def scenario_used_for_events(db_path: str) -> bool:
    manifest_path = Path(db_path).parent / "manifest.json"
    if not manifest_path.exists():
        # Older runs may not have a manifest; keep previous behavior.
        return True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(manifest.get("params", {}).get("use_generated_events", False))


def scenario_summary(
    db_path: str,
    scenario_summary_path: str | None = None,
    max_chars: int = 3000,
) -> str:
    if not scenario_used_for_events(db_path):
        return "Scenario seed context was not used to generate events for this run."
    candidates = []
    if scenario_summary_path:
        candidates.append(Path(scenario_summary_path))
    candidates.append(Path(db_path).parent / "scenario" / "scenario_summary.md")
    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            return text[:max_chars] if text else "Scenario summary is empty."
    return "No persisted scenario summary was found for this run."
