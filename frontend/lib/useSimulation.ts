"use client";
import { useCallback } from "react";
import { useSimStore } from "@/lib/store";
import type { SimEvent, SimParams } from "@/types/simulation";

export type { SimParams };

const WS_URL = "ws://localhost:8000/ws/simulate";

// Module-scoped, NOT per-hook-instance: the run socket must survive component
// unmounts. SimulationControl only lives on the Dashboard route — with the
// socket in a useRef, navigating away and back remounted the hook with a null
// ref, so Stop silently did nothing while the backend kept running.
let activeSocket: WebSocket | null = null;

function detach(ws: WebSocket) {
  ws.onopen = null;
  ws.onmessage = null;
  ws.onerror = null;
  ws.onclose = null;
}

export function useSimulation() {
  const start = useCallback((params: SimParams) => {
    // Detach handlers on any prior socket before closing it — its late
    // onclose/onerror could otherwise write status mid-start.
    const prev = activeSocket;
    if (prev) {
      detach(prev);
      try { prev.close(); } catch { /* noop */ }
      activeSocket = null;
    }

    // One atomic store transition (reset + status + totalSteps) so
    // subscribers see a single coherent update instead of three.
    useSimStore.getState().beginRun(params.n_steps);

    const ws = new WebSocket(WS_URL);
    activeSocket = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify(params));
    };

    ws.onmessage = (msg) => {
      let event: SimEvent;
      try {
        event = JSON.parse(msg.data as string) as SimEvent;
      } catch {
        return;
      }

      // Terminal events end the run: release the module-level handle so a
      // later stop() doesn't poke a dead socket.
      const finish = () => {
        if (activeSocket === ws) activeSocket = null;
        ws.close();
      };

      const s = useSimStore.getState();
      switch (event.type) {
        case "simulation_start":
          s.applyStart(event.simulation_id);
          break;
        case "step_start":
          s.applyStepStart(event.step, event.event_text);
          break;
        case "agent_action":
          s.applyAgentAction(event);
          break;
        case "trade":
          s.applyTrade(event);
          break;
        case "step_complete":
          s.applyStepComplete(event.step, event.balances, event.prices);
          break;
        case "simulation_complete":
          s.applyComplete(event.simulation_id, event.agent_names);
          finish();
          break;
        case "stopped":
          s.setStatus("idle");
          finish();
          break;
        case "error":
          s.setStatus("error");
          finish();
          break;
        case "heartbeat":
          break;
      }
    };

    ws.onerror = () => {
      if (useSimStore.getState().status === "running")
        useSimStore.getState().setStatus("error");
    };
    ws.onclose = () => {
      if (useSimStore.getState().status === "running")
        useSimStore.getState().setStatus("error");
    };
  }, []);

  const stop = useCallback(() => {
    const ws = activeSocket;
    // Drop our reference and flip to idle up front so the UI responds at once
    // and nothing reacts to this socket's late messages/close.
    activeSocket = null;
    useSimStore.getState().setStatus("idle");
    if (!ws) return;

    // Detach ALL handlers (onopen included — a still-connecting socket must
    // not send params after a stop) so in-flight events and the close event
    // are ignored — the run is over from the UI's point of view.
    detach(ws);

    // Ask the backend to abort the run, then close deterministically from our
    // side. Even if the stop frame doesn't flush, the backend's _watch_client
    // sees the disconnect and cancels — either path tears the simulation down.
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "stop" }));
      }
    } catch { /* noop */ }
    try { ws.close(); } catch { /* noop */ }
  }, []);

  return { start, stop };
}
