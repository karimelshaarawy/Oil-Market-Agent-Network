from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PriceAnchor:
    good_name: str
    low: float
    high: float
    rationale: str = ""

    def to_prompt_line(self) -> str:
        return (
            f"- {self.good_name}: {self.low:.2f}-{self.high:.2f} cr/unit"
            + (f" ({self.rationale})" if self.rationale else "")
        )


@dataclass(frozen=True)
class ScenarioEvent:
    step: int
    event_text: str | None
    source: str = "generated"


@dataclass(frozen=True)
class ScenarioPack:
    """Persisted, reproducible macro context for one simulation run."""

    summary: str
    macro_facts: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    price_anchors: list[PriceAnchor] = field(default_factory=list)
    events: list[ScenarioEvent] = field(default_factory=list)
    raw_seed_text: str = ""
    generated: bool = False
    source: str = "fallback"

    @property
    def events_by_step(self) -> dict[int, str | None]:
        return {event.step: event.event_text for event in self.events}

    def world_context_prompt(self) -> str:
        parts: list[str] = []
        if self.summary.strip():
            parts.append(self.summary.strip())
        if self.macro_facts:
            parts.append("Key facts:\n" + "\n".join(f"- {fact}" for fact in self.macro_facts))
        if self.uncertainties:
            parts.append(
                "Uncertainties:\n"
                + "\n".join(f"- {uncertainty}" for uncertainty in self.uncertainties)
            )
        return "\n\n".join(parts).strip()

    def price_anchor_prompt(self) -> str:
        if not self.price_anchors:
            return ""
        return "\n".join(anchor.to_prompt_line() for anchor in self.price_anchors)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def persist(self, scenario_dir: Path | str) -> dict[str, str]:
        scenario_dir = Path(scenario_dir)
        seed_dir = scenario_dir / "seed_docs"
        seed_dir.mkdir(parents=True, exist_ok=True)

        raw_path = seed_dir / "seed_context.txt"
        summary_path = scenario_dir / "scenario_summary.md"
        events_path = scenario_dir / "event_plan.json"
        anchors_path = scenario_dir / "price_anchors.json"
        pack_path = scenario_dir / "scenario_pack.json"

        raw_path.write_text(self.raw_seed_text or "", encoding="utf-8")
        summary_path.write_text(self._summary_markdown(), encoding="utf-8")
        events_path.write_text(
            json.dumps([asdict(event) for event in self.events], indent=2),
            encoding="utf-8",
        )
        anchors_path.write_text(
            json.dumps([asdict(anchor) for anchor in self.price_anchors], indent=2),
            encoding="utf-8",
        )
        pack_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

        return {
            "scenario_dir": str(scenario_dir),
            "raw_seed_path": str(raw_path),
            "summary_path": str(summary_path),
            "event_plan_path": str(events_path),
            "price_anchors_path": str(anchors_path),
            "pack_path": str(pack_path),
        }

    def _summary_markdown(self) -> str:
        lines = ["# Scenario Summary", "", self.summary.strip() or "No scenario summary."]
        if self.macro_facts:
            lines.extend(["", "## Macro Facts"])
            lines.extend(f"- {fact}" for fact in self.macro_facts)
        if self.uncertainties:
            lines.extend(["", "## Uncertainties"])
            lines.extend(f"- {uncertainty}" for uncertainty in self.uncertainties)
        if self.price_anchors:
            lines.extend(["", "## Price Anchors"])
            lines.extend(anchor.to_prompt_line() for anchor in self.price_anchors)
        return "\n".join(lines).strip() + "\n"
