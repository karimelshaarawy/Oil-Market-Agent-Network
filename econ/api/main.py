"""FastAPI app assembly for the econ backend.

Endpoint implementations live in the routers:
- econ/api/routers/simulation.py — WS /ws/simulate + GET /simulate/*
- econ/api/routers/chat.py       — POST /report/chat, /agent/{name}/chat

Simulation process management (spawn/stop/kill) lives in
econ/api/simulation_process.py.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from econ.api.routers import chat, simulation

# Re-exported for backward compatibility (tests patch these on this module).
from econ.api.simulation_process import (  # noqa: F401
    _DONE,
    _STOP_GRACE_SECONDS,
    _run_oil_inproc,
    _run_simulation,
    _sim_child_main,
)

app = FastAPI(title="Econ Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(simulation.router)
app.include_router(chat.router)


def main() -> None:
    import uvicorn
    # Scope the reloader to the source package only. Watching the whole repo
    # root makes watchfiles scan frontend/node_modules (~417MB), runs/ and the
    # chroma/.db files on every start and save, which dominates startup time.
    uvicorn.run(
        "econ.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["econ"],
    )


if __name__ == "__main__":
    main()
