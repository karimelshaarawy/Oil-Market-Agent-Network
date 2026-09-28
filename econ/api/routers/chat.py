"""Post-simulation chat endpoints: run-level report Q&A and agent interviews.

Responses stream as NDJSON (one JSON object per line), matching the frontend
client in frontend/lib/api.ts.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from econ.api.routers.simulation import _get_manifest
from econ.rag import ChromaSimulationMemory
from econ.report import PostSimulationInterviewService, ReportAgent

router = APIRouter()


def _rag_memory(chroma_dir: str) -> ChromaSimulationMemory:
    return ChromaSimulationMemory(
        persist_directory=chroma_dir,
        collection_name="econ_memory",
        enabled=True,
        reset_collection=False,
    )


@router.post("/report/chat")
async def report_chat(body: dict):
    simulation_id = body.get("simulation_id", "")
    message = body.get("message", "")
    if not simulation_id or not message.strip():
        return {"error": "simulation_id and message are required"}

    manifest = _get_manifest(simulation_id)
    if not manifest:
        return {"error": "Simulation not found"}

    db_path = str(manifest.get("db_path", ""))
    chroma_dir = str(manifest.get("chroma_dir", "chroma_oil_market"))
    rag = _rag_memory(chroma_dir)

    async def _stream() -> AsyncGenerator[bytes, None]:
        try:
            answer = ReportAgent(db_path=db_path, rag_memory=rag).answer(message)
            yield (json.dumps({"content": answer or "No response."}) + "\n").encode()
        except Exception as exc:
            yield (json.dumps({"error": str(exc)}) + "\n").encode()

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@router.post("/agent/{agent_name}/chat")
async def agent_chat(agent_name: str, body: dict):
    simulation_id = body.get("simulation_id", "")
    message = body.get("message", "")
    if not simulation_id or not message.strip():
        return {"error": "simulation_id and message are required"}

    manifest = _get_manifest(simulation_id)
    if not manifest:
        return {"error": "Simulation not found"}

    db_path = str(manifest.get("db_path", ""))
    chroma_dir = str(manifest.get("chroma_dir") or "")

    async def _stream() -> AsyncGenerator[bytes, None]:
        try:
            svc = PostSimulationInterviewService(
                db_path=db_path,
                chroma_dir=chroma_dir or None,
            )
            answer = svc.interview(agent_name=agent_name, question=message)
            yield (json.dumps({"content": answer or "No response."}) + "\n").encode()
        except Exception as exc:
            yield (json.dumps({"error": str(exc)}) + "\n").encode()

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
