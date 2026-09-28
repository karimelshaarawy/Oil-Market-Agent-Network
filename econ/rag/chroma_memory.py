from __future__ import annotations

import logging
import re
import sqlite3
from hashlib import sha1
from typing import TYPE_CHECKING, Any

from econ.core.config import DEFAULT_RAG_WINDOW_STEPS

if TYPE_CHECKING:
    from econ.economic_agent.agent import EconomicAgent
    from econ.economic_agent.agent_graph import AgentGraph
    from econ.economic_agent.config.agent_info import AgentInfo

logger = logging.getLogger("econ.rag")


class ChromaSimulationMemory:
    """Local Chroma-backed RAG memory for events, transactions, and reflections.

    SQLite remains the authoritative state store.  This class creates short
    text documents from selected SQLite facts and stores them in Chroma for
    semantic + keyword hybrid retrieval.
    """

    def __init__(
        self,
        persist_directory: str = "chroma_econ",
        collection_name: str = "econ_memory",
        top_k: int = 8,
        keyword_k: int = 4,
        window_steps: int = DEFAULT_RAG_WINDOW_STEPS,
        enabled: bool = True,
        reset_collection: bool = False,
    ) -> None:
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.top_k = top_k
        self.keyword_k = keyword_k
        self.window_steps = window_steps
        self.enabled = enabled
        self.client = None
        self.collection = None

        if not enabled:
            return

        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=persist_directory)
            if reset_collection:
                try:
                    self.client.delete_collection(collection_name)
                    logger.info("Reset Chroma collection %s", collection_name)
                except Exception:
                    # Chroma raises if the collection doesn't exist; that is fine
                    # for a fresh simulation run.
                    pass
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            self.enabled = False
            logger.warning(
                "Chroma RAG disabled; install chromadb or check local setup: %s",
                exc,
            )

    # ── Public API ──────────────────────────────────────────────────────

    def index_event(self, step: int, event_text: str | None) -> None:
        """Index a market event or event-clear marker."""
        if not self._ready:
            return

        text = (
            f"Step {step} market event cleared; market returned to neutral signals."
            if event_text is None
            else f"Step {step} market event: {event_text}"
        )
        event_hash = sha1(text.encode("utf-8")).hexdigest()[:12]
        self._upsert(
            doc_id=f"event:{step}:{event_hash}",
            document=text,
            metadata={
                "type": "event",
                "step": int(step),
                "agent_id": -1,
                "good_name": "",
                "region": "",
            },
        )

    def index_step(self, db: sqlite3.Connection, agent_graph: "AgentGraph", step: int) -> None:
        """Index deterministic step facts, such as completed transactions."""
        if not self._ready:
            return
        self._index_transactions(db, step)

    def index_agent_reflection(
        self,
        step: int,
        agent: "EconomicAgent",
        reflection: str,
    ) -> None:
        """Index an LLM-authored private reflection for one agent."""
        if not self._ready or not reflection.strip():
            return

        document = (
            f"Step {step} reflection by {agent.agent_info.name} "
            f"(agent {agent.economic_agent_id}, {agent.agent_info.agent_type}): "
            f"{reflection.strip()}"
        )
        reflection_hash = sha1(document.encode("utf-8")).hexdigest()[:12]
        self._upsert(
            doc_id=f"reflection:{step}:{agent.economic_agent_id}:{reflection_hash}",
            document=document,
            metadata={
                "type": "reflection",
                "step": int(step),
                "agent_id": int(agent.economic_agent_id),
                "good_name": "",
                "region": agent.agent_info.region or "",
            },
        )

    def retrieve_for_agent(self, agent_info: "AgentInfo", step: int) -> str:
        """Return a prompt-ready hybrid retrieval section for one agent."""
        if not self._ready:
            return ""

        keywords = self._keywords_for_agent(agent_info)
        query = self._query_for_agent(agent_info, keywords)
        where = self._step_window_filter(step)

        docs: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()

        # Semantic branch: Chroma vector search.  Keep Chroma order as-is.
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=max(self.top_k, 1),
                where=where,
                include=["documents", "metadatas"],
            )
            for doc, meta in zip(
                results.get("documents", [[]])[0],
                results.get("metadatas", [[]])[0],
            ):
                if doc and doc not in seen:
                    seen.add(doc)
                    docs.append((doc, dict(meta or {})))
        except Exception as exc:
            logger.warning("semantic retrieval failed: %s", exc)

        # Keyword branch: exact substring matching over the same recency window.
        # No reranking is applied; semantic results keep priority, then keyword
        # matches are appended in reverse chronological order.
        try:
            candidates = self.collection.get(
                where=where,
                include=["documents", "metadatas"],
            )
            keyword_docs: list[tuple[str, dict[str, Any]]] = []
            for doc, meta in zip(
                candidates.get("documents", []),
                candidates.get("metadatas", []),
            ):
                if not doc or doc in seen:
                    continue
                text = doc.lower()
                if any(k and k.lower() in text for k in keywords):
                    keyword_docs.append((doc, dict(meta or {})))
            keyword_docs.sort(key=lambda item: int(item[1].get("step", 0)), reverse=True)
            for doc, meta in keyword_docs[: self.keyword_k]:
                if doc not in seen:
                    seen.add(doc)
                    docs.append((doc, meta))
        except Exception as exc:
            logger.warning("keyword retrieval failed: %s", exc)

        if not docs:
            return "RETRIEVED MEMORY:\n  No relevant memories found yet."

        lines = [f"  - {doc}" for doc, _ in docs[: self.top_k]]
        return (
            "RETRIEVED MEMORY (hybrid semantic + keyword; recent relevant "
            "events, transactions, and reflections):\n"
            + "\n".join(lines)
        )

    def retrieve_for_query(
        self,
        query: str,
        step: int | None = None,
        top_k: int | None = None,
    ) -> str:
        """Return hybrid retrieval context for an arbitrary report question."""
        if not self._ready:
            return ""

        limit = top_k or self.top_k
        where = self._step_window_filter(step) if step is not None else None
        docs: list[str] = []
        seen: set[str] = set()

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": max(limit, 1),
                "include": ["documents", "metadatas"],
            }
            if where is not None:
                kwargs["where"] = where
            results = self.collection.query(**kwargs)
            for doc in results.get("documents", [[]])[0]:
                if doc and doc not in seen:
                    seen.add(doc)
                    docs.append(doc)
        except Exception as exc:
            logger.warning("report semantic retrieval failed: %s", exc)

        try:
            kwargs = {"include": ["documents", "metadatas"]}
            if where is not None:
                kwargs["where"] = where
            candidates = self.collection.get(**kwargs)
            query_terms = [t.lower() for t in re.findall(r"[A-Za-z_]{3,}", query)]
            keyword_hits: list[tuple[int, str]] = []
            for doc, meta in zip(
                candidates.get("documents", []),
                candidates.get("metadatas", []),
            ):
                if not doc or doc in seen:
                    continue
                lowered = doc.lower()
                if any(term in lowered for term in query_terms):
                    keyword_hits.append((int((meta or {}).get("step", 0)), doc))
            keyword_hits.sort(key=lambda item: item[0], reverse=True)
            for _, doc in keyword_hits[: self.keyword_k]:
                if doc not in seen:
                    seen.add(doc)
                    docs.append(doc)
        except Exception as exc:
            logger.warning("report keyword retrieval failed: %s", exc)

        if not docs:
            return "No relevant RAG memories found."
        return "\n".join(f"- {doc}" for doc in docs[:limit])

    # ── Indexing helpers ────────────────────────────────────────────────

    @property
    def _ready(self) -> bool:
        return self.enabled and self.collection is not None

    def _index_transactions(self, db: sqlite3.Connection, step: int) -> None:
        rows = db.execute(
            """
            SELECT mt.transaction_id, mt.buyer_id, buyer.name AS buyer_name,
                   mt.seller_id, seller.name AS seller_name, mt.good_name,
                   mt.price, mt.quantity, mt.total_paid, mt.timestamp
            FROM market_transaction mt
            JOIN agent buyer ON buyer.agent_id = mt.buyer_id
            JOIN agent seller ON seller.agent_id = mt.seller_id
            WHERE mt.timestamp = ?
            ORDER BY mt.transaction_id
            """,
            (step,),
        ).fetchall()
        for row in rows:
            document = (
                f"Step {row['timestamp']} transaction: {row['buyer_name']} "
                f"(agent {row['buyer_id']}) bought {row['quantity']} units of "
                f"{row['good_name']} from {row['seller_name']} "
                f"(agent {row['seller_id']}) at {row['price']:.2f} cr/unit; "
                f"total paid {row['total_paid']:.2f} credits."
            )
            self._upsert(
                doc_id=f"tx:{row['transaction_id']}",
                document=document,
                metadata={
                    "type": "transaction",
                    "step": int(row["timestamp"]),
                    "agent_id": -1,
                    "buyer_id": int(row["buyer_id"]),
                    "seller_id": int(row["seller_id"]),
                    "good_name": row["good_name"],
                    "region": "",
                },
            )

    def _index_reflections(
        self,
        db: sqlite3.Connection,
        agent_graph: "AgentGraph",
        step: int,
    ) -> None:
        for agent_id, agent in agent_graph.get_agents():
            agent_row = db.execute(
                "SELECT balance FROM agent WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
            if agent_row is None:
                continue

            actions = db.execute(
                "SELECT action, COUNT(*) AS n FROM trace "
                "WHERE agent_id = ? AND timestamp = ? GROUP BY action ORDER BY action",
                (agent_id, step),
            ).fetchall()
            ledger_rows = db.execute(
                "SELECT amount FROM financial_ledger WHERE agent_id = ? AND step = ?",
                (agent_id, step),
            ).fetchall()
            debt = db.execute(
                "SELECT COALESCE(SUM(amount), 0) AS debt FROM loan "
                "WHERE borrower_id = ? AND repaid = 0",
                (agent_id,),
            ).fetchone()

            action_text = (
                ", ".join(f"{r['action']} x{r['n']}" for r in actions)
                if actions
                else "no recorded actions"
            )
            income = sum(r["amount"] for r in ledger_rows if r["amount"] > 0)
            expenses = sum(-r["amount"] for r in ledger_rows if r["amount"] < 0)
            net = income - expenses
            debt_amount = float(debt["debt"] or 0.0)

            document = (
                f"Step {step} reflection for {agent.agent_info.name} "
                f"(agent {agent_id}, {agent.agent_info.agent_type}): actions were "
                f"{action_text}; step income {income:.2f}, expenses {expenses:.2f}, "
                f"net cash flow {net:.2f}; ending balance {float(agent_row['balance']):.2f}; "
                f"outstanding debt {debt_amount:.2f}."
            )
            self._upsert(
                doc_id=f"reflection:{step}:{agent_id}",
                document=document,
                metadata={
                    "type": "reflection",
                    "step": int(step),
                    "agent_id": int(agent_id),
                    "good_name": "",
                    "region": agent.agent_info.region or "",
                },
            )

    def _upsert(self, doc_id: str, document: str, metadata: dict[str, Any]) -> None:
        try:
            self.collection.upsert(
                ids=[doc_id],
                documents=[document],
                metadatas=[self._clean_metadata(metadata)],
            )
        except Exception as exc:
            logger.warning("RAG upsert failed for %s: %s", doc_id, exc)

    # ── Retrieval helpers ────────────────────────────────────────────────

    def _step_window_filter(self, step: int) -> dict[str, Any]:
        lower = max(0, int(step) - self.window_steps)
        return {
            "$and": [
                {"step": {"$gte": lower}},
                {"step": {"$lte": int(step)}},
            ]
        }

    def _keywords_for_agent(self, agent_info: "AgentInfo") -> list[str]:
        profile = agent_info.profile or {}
        goods = set(profile.get("produces", []) or [])
        goods.update(profile.get("inputs", []) or [])
        if agent_info.agent_type == "refiner":
            goods.update({"crude_oil", "refined_fuel", "diesel"})
        if agent_info.agent_type in {"speculator", "consumer"}:
            goods.update({"crude_oil", "refined_fuel"})
        if agent_info.agent_type == "bank":
            goods.update({"loan", "debt", "borrow", "repay", "balance"})

        return [
            agent_info.name,
            str(agent_info.agent_id),
            agent_info.agent_type,
            agent_info.sector,
            agent_info.region or "",
            *sorted(goods),
            "event",
            "transaction",
            "reflection",
        ]

    def _query_for_agent(self, agent_info: "AgentInfo", keywords: list[str]) -> str:
        goods = ", ".join(k for k in keywords if self._looks_like_good(k)) or "market goods"
        if agent_info.agent_type == "firm":
            intent = "recent clearing prices, major buyers, stale inventory, and demand shocks"
        elif agent_info.agent_type == "refiner":
            intent = "cheap input crude, refined output prices, crack spread, and refinery margins"
        elif agent_info.agent_type == "speculator":
            intent = "price spikes, price dips, resale opportunities, and event-driven trades"
        elif agent_info.agent_type == "consumer":
            intent = "cheap purchase opportunities, supply shortages, and price trends"
        elif agent_info.agent_type == "bank":
            intent = "borrower cash flow, outstanding debt, loan risk, and repayment behaviour"
        else:
            intent = "market events, transactions, and agent financial outcomes"

        return (
            f"Relevant simulation memory for {agent_info.name}, a "
            f"{agent_info.agent_type} in {agent_info.sector}. Focus on {intent}. "
            f"Relevant goods and topics: {goods}."
        )

    @staticmethod
    def _looks_like_good(value: str) -> bool:
        return bool(re.search(r"oil|fuel|diesel|loan|debt|balance", value or ""))

    @staticmethod
    def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            if value is None:
                clean[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                clean[key] = value
            else:
                clean[key] = str(value)
        return clean
