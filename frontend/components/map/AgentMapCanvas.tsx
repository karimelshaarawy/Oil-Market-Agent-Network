"use client";
import React, { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  useNodesState,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTheme } from "next-themes";
import { Waypoints } from "lucide-react";
import { useSimStore } from "@/lib/store";
import { api } from "@/lib/api";
import { CATEGORY_BY_TYPE } from "@/lib/defaultAgents";
import {
  PULSE_MAX_AGE_STEPS,
  eventId,
  layoutPositions,
  pulseColor,
  pulseFromLoan,
  pulseFromTrade,
  type ActionBadge,
  type MapAgent,
  type Pulse,
} from "@/lib/mapModel";
import { AgentNode, type AgentNodeType } from "@/components/map/AgentNode";
import { TradeEdge, type TradeEdgeType } from "@/components/map/TradeEdge";
import { MapOverlay } from "@/components/map/MapOverlay";
import { AgentSlideOver } from "@/components/map/AgentSlideOver";
import { MapTransportBar } from "@/components/map/MapTransportBar";
import type { AgentActionEvent, AgentTypeName, TradeEvent } from "@/types/simulation";

const nodeTypes = { agent: AgentNode };
const edgeTypes = { trade: TradeEdge };

/** Actions that animate as agent-to-agent pulses rather than node badges. */
const LOAN_ACTIONS = new Set(["borrow", "repay"]);

const BADGE_LABELS: Record<string, (e: AgentActionEvent) => string> = {
  produce: (e) => `Produced ${e.qty ?? ""} ${e.good ?? ""}`.trim(),
  refine: (e) => `Refined → ${e.qty ?? ""} ${e.good ?? ""}`.trim(),
  list_good: (e) => `Listed ${e.qty ?? ""} ${e.good ?? ""} @ $${e.price?.toFixed(2) ?? "?"}`,
};

function toMapAgent(name: string, agentType?: string, sector?: string, region?: string): MapAgent {
  const type = (agentType ?? "unknown") as AgentTypeName;
  return {
    name,
    agentType: type in CATEGORY_BY_TYPE ? type : "unknown",
    category: CATEGORY_BY_TYPE[type] ?? "unknown",
    sector,
    region,
  };
}

export function AgentMapCanvas() {
  const { resolvedTheme } = useTheme();
  const feed = useSimStore((s) => s.feed);
  const status = useSimStore((s) => s.status);
  const agentNames = useSimStore((s) => s.agentNames);
  const customAgents = useSimStore((s) => s.params.custom_agents);
  const currentStep = useSimStore((s) => s.currentStep);
  const simulationId = useSimStore((s) => s.simulationId);
  const eventLog = useSimStore((s) => s.eventLog);
  const stepEvents = useSimStore((s) => s.stepEvents);

  const [selected, setSelected] = useState<string | null>(null);
  // History scrub position into eventLog; null = following live.
  const [cursor, setCursor] = useState<number | null>(null);
  const [apiAgents, setApiAgents] = useState<MapAgent[]>([]);
  const [staticPairs, setStaticPairs] = useState<Array<{ source: string; target: string; good: string }>>([]);

  // ── roster ────────────────────────────────────────────────────────────────
  // Live run: store agent names enriched with profiles from the launch roster
  // (or REST metadata). Idle: latest simulation's agents + their traded pairs.
  useEffect(() => {
    let cancelled = false;
    const load = async (simId: string, withStaticEdges: boolean) => {
      try {
        const { agents } = await api.listAgents(simId);
        if (cancelled) return;
        setApiAgents(agents.map((a) => toMapAgent(a.name, a.agent_type, a.sector)));
        if (withStaticEdges) {
          const snap = await api.snapshot(simId);
          if (cancelled) return;
          const pairs = new Map<string, { source: string; target: string; good: string }>();
          for (const t of snap.transactions) {
            pairs.set(`${t.seller}→${t.buyer}|${t.good_name}`, {
              source: t.seller,
              target: t.buyer,
              good: t.good_name,
            });
          }
          setStaticPairs(Array.from(pairs.values()));
        }
      } catch {
        /* backend not running or no sims yet — map just shows the empty state */
      }
    };

    if (simulationId) {
      load(simulationId, false);
    } else if (agentNames.length === 0) {
      api
        .listSimulations()
        .then(({ simulations }) => {
          if (cancelled || simulations.length === 0) return;
          load(simulations[simulations.length - 1], true);
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [simulationId, agentNames.length]);

  const roster = useMemo<MapAgent[]>(() => {
    const profileByName = new Map(
      customAgents.map((p) => [
        p.name,
        { name: p.name, agentType: p.agent_type, category: p.category, sector: p.sector, region: p.region } as MapAgent,
      ]),
    );
    const apiByName = new Map(apiAgents.map((a) => [a.name, a]));
    // A run launched from this UI always uses the custom roster, so it can be
    // shown in full from step 0 instead of trickling in event-by-event.
    if (status === "running" && customAgents.length > 0) {
      const out = Array.from(profileByName.values());
      for (const name of agentNames) {
        if (!profileByName.has(name)) out.push(apiByName.get(name) ?? toMapAgent(name));
      }
      return out;
    }
    if (agentNames.length > 0) {
      return agentNames.map(
        (name) => profileByName.get(name) ?? apiByName.get(name) ?? toMapAgent(name),
      );
    }
    return apiAgents;
  }, [agentNames, customAgents, apiAgents, status]);

  const rosterNames = useMemo(() => new Set(roster.map((a) => a.name)), [roster]);
  const isLive = agentNames.length > 0 || status === "running";

  // ── history mode ──────────────────────────────────────────────────────────
  // Clamp rather than reset (the log only shrinks when a new run clears it).
  const historyIndex =
    cursor === null || eventLog.length === 0 ? null : Math.min(cursor, eventLog.length - 1);
  const focused = historyIndex === null ? null : eventLog[historyIndex];

  // All events of the focused step — the faint context around the bright event.
  const focusedStepEvents = useMemo<Array<AgentActionEvent | TradeEvent>>(() => {
    if (!focused) return [];
    return eventLog.filter((e) => e.step === focused.step);
  }, [eventLog, focused]);

  // Balances as of the scrub position: fold the balances events carry over the
  // log prefix; agents with no event yet show their earliest known balance.
  const historyBalances = useMemo<Record<string, number> | null>(() => {
    if (historyIndex === null) return null;
    const record = (out: Record<string, number>, e: AgentActionEvent | TradeEvent, overwrite: boolean) => {
      if (e.type === "trade") {
        if (e.buyer_balance !== undefined && (overwrite || out[e.buyer] === undefined)) out[e.buyer] = e.buyer_balance;
        if (e.seller_balance !== undefined && (overwrite || out[e.seller] === undefined)) out[e.seller] = e.seller_balance;
      } else if (e.balance !== undefined && (overwrite || out[e.agent] === undefined)) {
        out[e.agent] = e.balance;
      }
    };
    const balances: Record<string, number> = {};
    for (const e of eventLog) record(balances, e, false);
    for (let i = 0; i <= historyIndex; i++) record(balances, eventLog[i], true);
    return balances;
  }, [eventLog, historyIndex]);

  // ── interactions derived from the live feed ───────────────────────────────
  // Feed is newest-first with non-increasing steps, so iteration can stop at
  // the lingering-window cutoff. One edge per (pair, kind, good): the newest
  // pulse wins; its particle animation runs once on mount and self-terminates.
  const pulses = useMemo<Pulse[]>(() => {
    const cutoff = currentStep - PULSE_MAX_AGE_STEPS;
    const latestPerPair = new Map<string, Pulse>();
    for (const e of feed) {
      if (e.step < cutoff) break;
      const p = e.type === "trade" ? pulseFromTrade(e) : LOAN_ACTIONS.has(e.action) ? pulseFromLoan(e) : null;
      if (!p) continue;
      const key = `${p.source}→${p.target}|${p.kind}|${p.good ?? ""}`;
      if (!latestPerPair.has(key)) latestPerPair.set(key, p);
    }
    return Array.from(latestPerPair.values());
  }, [feed, currentStep]);

  // Live: latest solo action per agent within the current step; the badge
  // fades out via CSS and a new action restarts it (keyed by id).
  // History: the focused solo action persists bright; other same-step solo
  // actions persist faint.
  const badges = useMemo<Record<string, ActionBadge>>(() => {
    const out: Record<string, ActionBadge> = {};
    if (focused) {
      for (const e of focusedStepEvents) {
        if (e.type !== "agent_action" || LOAN_ACTIONS.has(e.action)) continue;
        out[e.agent] = {
          id: eventId(e),
          action: e.action,
          text: BADGE_LABELS[e.action]?.(e) ?? e.summary,
          persist: true,
          dim: true,
        };
      }
      if (focused.type === "agent_action" && !LOAN_ACTIONS.has(focused.action)) {
        out[focused.agent] = {
          id: eventId(focused),
          action: focused.action,
          text: BADGE_LABELS[focused.action]?.(focused) ?? focused.summary,
          persist: true,
        };
      }
      return out;
    }
    for (const e of feed) {
      if (e.step < currentStep) break;
      if (e.type !== "agent_action" || LOAN_ACTIONS.has(e.action)) continue;
      if (out[e.agent]) continue;
      out[e.agent] = {
        id: eventId(e),
        action: e.action,
        text: BADGE_LABELS[e.action]?.(e) ?? e.summary,
      };
    }
    return out;
  }, [feed, currentStep, focused, focusedStepEvents]);

  // ── nodes (draggable; positions preserved across data updates) ────────────
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNodeType>([]);

  useEffect(() => {
    setNodes((prev) => {
      const prevPos = new Map(prev.map((n) => [n.id, n.position]));
      const layout = layoutPositions(roster);
      return roster.map((agent) => ({
        id: agent.name,
        type: "agent" as const,
        position: prevPos.get(agent.name) ?? layout[agent.name],
        data: { agent, badge: null, selected: false },
      }));
    });
  }, [roster, setNodes]);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => {
        const badge = badges[n.id] ?? null;
        const isSelected = selected === n.id;
        const balanceOverride = historyBalances ? historyBalances[n.id] ?? null : undefined;
        if (
          n.data.badge === badge &&
          n.data.selected === isSelected &&
          n.data.balanceOverride === balanceOverride
        )
          return n;
        return { ...n, data: { ...n.data, badge, selected: isSelected, balanceOverride } };
      }),
    );
  }, [badges, selected, historyBalances, setNodes]);

  // ── edges ─────────────────────────────────────────────────────────────────
  const edges = useMemo<TradeEdgeType[]>(() => {
    const toEdge = (p: Pulse, variant: "live" | "focus" | "context", idPrefix = ""): TradeEdgeType => {
      const color = pulseColor(p);
      return {
        id: `${idPrefix}${p.id}`,
        source: p.source,
        target: p.target,
        type: "trade" as const,
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 13, height: 13 },
        data: {
          color,
          variant,
          // Trades label the product; loans label the kind + amount.
          label: p.kind === "trade" ? p.good : p.label,
        },
      };
    };
    const onMap = (p: Pulse) => rosterNames.has(p.source) && rosterNames.has(p.target);
    const pairKey = (p: Pulse) => `${p.source}→${p.target}|${p.kind}|${p.good ?? ""}`;

    // History mode: the focused interaction bright (particle replays on every
    // scrub move via the remounting id), its step's other interactions faint.
    if (focused) {
      const focusPulse =
        focused.type === "trade"
          ? pulseFromTrade(focused)
          : LOAN_ACTIONS.has(focused.action)
            ? pulseFromLoan(focused)
            : null;
      const out: TradeEdgeType[] = [];
      const seenPairs = new Set<string>(focusPulse ? [pairKey(focusPulse)] : []);
      for (const e of focusedStepEvents) {
        if (e === focused) continue;
        const p = e.type === "trade" ? pulseFromTrade(e) : LOAN_ACTIONS.has(e.action) ? pulseFromLoan(e) : null;
        if (!p || !onMap(p) || seenPairs.has(pairKey(p))) continue;
        seenPairs.add(pairKey(p));
        out.push(toEdge(p, "context", "ctx-"));
      }
      if (focusPulse && onMap(focusPulse)) out.push(toEdge(focusPulse, "focus", "focus-"));
      return out;
    }

    if (!isLive && staticPairs.length > 0) {
      return staticPairs
        .filter((p) => rosterNames.has(p.source) && rosterNames.has(p.target))
        .map((p, i) => ({
          id: `static-${i}`,
          source: p.source,
          target: p.target,
          type: "trade" as const,
          data: {
            color: pulseColor({ kind: "trade", good: p.good }),
            variant: "static" as const,
          },
        }));
    }

    return pulses.filter(onMap).map((p) => toEdge(p, "live"));
  }, [pulses, isLive, staticPairs, rosterNames, focused, focusedStepEvents]);

  const onNodeClick: NodeMouseHandler<AgentNodeType> = (_, node) => {
    setSelected((cur) => (cur === node.id ? null : node.id));
  };

  const selectedAgent = selected ? roster.find((a) => a.name === selected) ?? null : null;

  if (roster.length === 0) {
    return (
      <div className="h-full rounded-xl border border-dashed border-border/80 bg-secondary/5 flex flex-col items-center justify-center gap-3 select-none">
        <div className="p-3 rounded-full bg-rose-500/5 border border-rose-500/10 shadow-[0_0_15px_rgba(244,63,94,0.1)] text-rose-500/60 animate-pulse">
          <Waypoints className="h-8 w-8" />
        </div>
        <p className="text-muted-foreground text-sm max-w-xs text-center leading-normal">
          No agents to map yet. Run a simulation from the Dashboard and watch the network come alive.
        </p>
      </div>
    );
  }

  return (
    <div className="relative h-full rounded-xl border border-border overflow-hidden bg-white/50 dark:bg-slate-950/50 backdrop-blur-sm shadow-sm">
      <MapOverlay
        history={
          focused && historyIndex !== null
            ? {
                index: historyIndex,
                total: eventLog.length,
                step: focused.step,
                headline: stepEvents[focused.step] ?? null,
              }
            : null
        }
      />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onPaneClick={() => setSelected(null)}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.3}
        maxZoom={1.8}
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: true }}
        style={{ background: "transparent" }}
      >
        <Background variant={BackgroundVariant.Dots} gap={28} size={1.5} className="opacity-50" />
        <Controls showInteractive={false} />
      </ReactFlow>
      {eventLog.length > 0 && (
        <MapTransportBar
          total={eventLog.length}
          cursor={historyIndex}
          onChange={setCursor}
          summary={focused?.summary ?? null}
          status={status}
        />
      )}
      {selectedAgent && <AgentSlideOver agent={selectedAgent} onClose={() => setSelected(null)} />}
    </div>
  );
}
