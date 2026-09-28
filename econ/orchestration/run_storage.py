from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SimulationRunPaths:
    simulation_id: str
    run_dir: Path
    db_path: Path
    chroma_dir: Path
    scenario_dir: Path
    manifest_path: Path


DEFAULT_RUNS_DIR = Path("runs")


def create_run_paths(
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    db_filename: str = "simulation.db",
    chroma_dirname: str = "chroma",
    scenario_dirname: str = "scenario",
) -> SimulationRunPaths:
    runs_dir = Path(runs_dir)
    simulation_id = uuid.uuid4().hex
    run_dir = runs_dir / simulation_id
    run_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir = run_dir / chroma_dirname
    scenario_dir = run_dir / scenario_dirname
    db_path = run_dir / db_filename
    manifest_path = run_dir / "manifest.json"
    return SimulationRunPaths(
        simulation_id=simulation_id,
        run_dir=run_dir,
        db_path=db_path,
        chroma_dir=chroma_dir,
        scenario_dir=scenario_dir,
        manifest_path=manifest_path,
    )


def write_manifest(paths: SimulationRunPaths, manifest: dict[str, Any]) -> None:
    data = {
        "simulation_id": paths.simulation_id,
        "created_at_unix": int(time.time()),
        "run_dir": str(paths.run_dir),
        "db_path": str(paths.db_path),
        "chroma_dir": str(paths.chroma_dir),
        "scenario_dir": str(paths.scenario_dir),
        **manifest,
    }
    paths.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_simulation_ids(runs_dir: Path | str = DEFAULT_RUNS_DIR) -> list[str]:
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return []
    ids: list[str] = []
    for child in runs_dir.iterdir():
        if child.is_dir() and (child / "manifest.json").exists():
            ids.append(child.name)
    ids.sort(reverse=True)
    return ids


def read_manifest(simulation_id: str, runs_dir: Path | str = DEFAULT_RUNS_DIR) -> dict[str, Any]:
    runs_dir = Path(runs_dir)
    manifest_path = runs_dir / simulation_id / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))

