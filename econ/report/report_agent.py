from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

from econ.core.config import get_api_base_url, get_api_key
from econ.core.thinking_adapter import adapt_openai_client_call
from econ.economic_platform.read_queries import SimulationDBReader
from econ.rag import ChromaSimulationMemory
from econ.report.run_artifacts import scenario_summary

load_dotenv(override=True)


@dataclass
class ReportContext:
    """Exact SQLite facts plus semantic RAG context for a report answer."""

    question: str
    scenario_context: str
    sql_summary: str
    rag_context: str


class ReportAgent:
    """Read-only analyst agent for post-simulation questions.

    The ReportAgent is not part of the market. It combines exact SQLite facts
    with Chroma retrieval context, then asks the configured LLM for an answer.
    """

    def __init__(
        self,
        db_path: str,
        rag_memory: ChromaSimulationMemory | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        scenario_summary_path: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.reader = SimulationDBReader(db_path)
        self.rag_memory = rag_memory
        self.scenario_summary_path = scenario_summary_path
        self.model_name = model_name or os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.client = OpenAI(
            base_url=base_url or get_api_base_url(),
            api_key=api_key or get_api_key(),
            timeout=timeout_seconds or float(os.getenv("ECON_REPORT_TIMEOUT_SECONDS", "60")),
        )

    def answer(self, question: str) -> str:
        context = self.build_context(question)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a careful economic simulation report agent. "
                    "Use SQLite facts as authoritative. Use RAG memories for "
                    "agent reasoning, events, and transaction context. If facts "
                    "are missing, say so. Be concise and cite concrete numbers."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{context.question}\n\n"
                    f"SCENARIO CONTEXT:\n{context.scenario_context}\n\n"
                    f"SQL FACTS:\n{context.sql_summary}\n\n"
                    f"RELEVANT RAG MEMORY:\n{context.rag_context}\n\n"
                    "Answer the question in clear engineering/economic prose."
                ),
            },
        ]
        response = adapt_openai_client_call(
            self.client,
            self.model_name,
            messages=messages,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def build_context(self, question: str) -> ReportContext:
        max_step = self.reader.max_step()
        rag_context = (
            self.rag_memory.retrieve_for_query(question, step=max_step, top_k=10)
            if self.rag_memory is not None
            else "RAG memory is not available."
        )
        reader = self.reader
        return ReportContext(
            question=question,
            scenario_context=scenario_summary(
                self.db_path, self.scenario_summary_path, max_chars=3000
            ),
            sql_summary="\n\n".join(
                [
                    "Balances after debt:\n" + self._format_rows(reader.balances_after_debt_rows()),
                    "Transaction summary by good:\n" + self._format_rows(reader.transaction_summary_rows()),
                    "Average transaction price by step:\n" + self._format_rows(reader.price_by_step_rows()),
                    "Loans:\n" + self._format_rows(reader.loan_summary_rows()),
                    "Recent agent reflections:\n" + self._format_rows(reader.reflection_overview_rows()),
                ]
            ),
            rag_context=rag_context,
        )

    @staticmethod
    def _format_rows(rows: list[sqlite3.Row]) -> str:
        if not rows:
            return "  none"
        lines = []
        for row in rows:
            lines.append(
                "  - " + ", ".join(f"{key}={row[key]}" for key in row.keys())
            )
        return "\n".join(lines)
