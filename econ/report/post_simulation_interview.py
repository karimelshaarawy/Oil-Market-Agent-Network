from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI

from econ.core.config import (
    DEFAULT_INTERVIEW_MAX_LEDGER_ENTRIES,
    DEFAULT_INTERVIEW_MAX_REFLECTIONS,
    get_api_base_url,
    get_api_key,
)
from econ.core.thinking_adapter import adapt_openai_client_call
from econ.economic_platform.read_queries import SimulationDBReader
from econ.rag import ChromaSimulationMemory
from econ.report.run_artifacts import scenario_summary


@dataclass(frozen=True)
class InterviewConfig:
    model_name: str
    timeout_seconds: float
    max_reflections: int = DEFAULT_INTERVIEW_MAX_REFLECTIONS
    max_ledger_entries: int = DEFAULT_INTERVIEW_MAX_LEDGER_ENTRIES
    rag_top_k: int = 10


class PostSimulationInterviewService:
    """Interview agents after a simulation from persisted state (no live objects).

    This mirrors MiroFish's approach: agents are *rehydrated* from stored
    artifacts (SQLite facts + vector memories) rather than kept alive in RAM.
    """

    def __init__(
        self,
        db_path: str,
        chroma_dir: str | None = None,
        scenario_summary_path: str | None = None,
        config: InterviewConfig | None = None,
    ) -> None:
        self.db_path = db_path
        self.reader = SimulationDBReader(db_path)
        self.chroma_dir = chroma_dir
        self.scenario_summary_path = scenario_summary_path
        self.config = config or InterviewConfig(
            model_name=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            timeout_seconds=float(os.getenv("ECON_INTERVIEW_TIMEOUT_SECONDS", "60")),
        )
        self.client = OpenAI(
            base_url=get_api_base_url(),
            api_key=get_api_key(),
            timeout=self.config.timeout_seconds,
        )
        self.rag_memory = (
            ChromaSimulationMemory(
                persist_directory=chroma_dir or "chroma_econ",
                collection_name="econ_memory",
                enabled=bool(chroma_dir),
                reset_collection=False,
                top_k=self.config.rag_top_k,
            )
            if chroma_dir
            else None
        )

    def interview(self, agent_name: str, question: str) -> str:
        if not agent_name.strip():
            return "No agent selected."
        if not question.strip():
            return "Ask a non-empty question."

        agent = self.reader.agent_row(agent_name)
        if agent is None:
            return f"Unknown agent: {agent_name}"

        max_step = self.reader.max_step()
        reflections = self._recent_reflections(agent["agent_id"])
        ledger = self._recent_ledger(agent["agent_id"])
        scenario_context = scenario_summary(
            self.db_path, self.scenario_summary_path, max_chars=2500
        )
        rag = (
            self.rag_memory.retrieve_for_query(
                query=f"{agent_name} ({agent['agent_type']}) {question}",
                step=max_step,
                top_k=self.config.rag_top_k,
            )
            if self.rag_memory is not None
            else ""
        )

        sys = (
            "You are being interviewed after an economic simulation.\n"
            "Roleplay as the agent described below.\n"
            "Use ONLY the provided facts/memories; do not invent transactions.\n"
            "If you are uncertain, say what you remember and what you do not know.\n"
            "Be concise (3-8 sentences) unless the question asks for detail."
        )
        user = (
            "AGENT PROFILE:\n"
            f"- name: {agent['name']}\n"
            f"- type: {agent['agent_type']}\n"
            f"- sector: {agent['sector']}\n"
            f"- region: {agent['region']}\n\n"
            f"SIMULATION MAX STEP: {max_step}\n\n"
            "SCENARIO CONTEXT:\n"
            + scenario_context
            + "\n\n"
            "RECENT REFLECTIONS (most recent first):\n"
            + (reflections or "  (none)\n")
            + "\nRECENT CASHFLOWS (ledger; revenue excludes transport fees):\n"
            + (ledger or "  (none)\n")
            + ("\nRAG MEMORY (events/tx/reflections):\n" + (rag or "(none)") if rag else "")
            + "\n\nQUESTION:\n"
            + question.strip()
        )

        resp = adapt_openai_client_call(
            self.client,
            self.config.model_name,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

    # ── Prompt-section formatting ───────────────────────────────────────

    def _recent_reflections(self, agent_id: int) -> str:
        rows = self.reader.recent_reflection_rows(
            agent_id, self.config.max_reflections
        )
        if not rows:
            return ""
        return "\n".join([f"  - step={r['step']}: {r['reflection']}" for r in rows])

    def _recent_ledger(self, agent_id: int) -> str:
        rows = self.reader.recent_ledger_rows(
            agent_id, self.config.max_ledger_entries
        )
        if not rows:
            return ""
        lines = []
        for r in rows:
            sign = "+" if float(r["amount"]) > 0 else ""
            lines.append(f"  - step={r['step']}: {r['category']} {sign}{r['amount']}: {r['description']}")
        return "\n".join(lines)
