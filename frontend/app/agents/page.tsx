"use client";
import { useEffect, useMemo, useState } from "react";
import { useSimStore } from "@/lib/store";
import { AgentCard } from "@/components/AgentCard";
import { api } from "@/lib/api";
import { Loader2, Bot } from "lucide-react";

export default function AgentsPage() {
  const agentNames = useSimStore((s) => s.agentNames);
  const agentStates = useSimStore((s) => s.agentStates);
  const balances = useSimStore((s) => s.balances);
  const status = useSimStore((s) => s.status);
  const simulationId = useSimStore((s) => s.simulationId);

  const [apiNames, setApiNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [agentMetadata, setAgentMetadata] = useState<Record<string, { agent_type: string; sector: string }>>({});

  const storeNames = useMemo(() => {
    if (agentNames.length > 0) return agentNames;
    const names = new Set([
      ...Object.keys(agentStates),
      ...Object.keys(balances),
    ]);
    return Array.from(names).sort();
  }, [agentNames, agentStates, balances]);

  useEffect(() => {
    const fetchMetadata = async (simId: string) => {
      try {
        const res = await api.listAgents(simId);
        if (res && res.agents) {
          const meta: Record<string, { agent_type: string; sector: string }> = {};
          res.agents.forEach((a) => {
            meta[a.name] = { agent_type: a.agent_type, sector: a.sector };
          });
          setAgentMetadata((prev) => ({ ...prev, ...meta }));
        }
      } catch (err) {
        console.error("Failed to fetch agent metadata", err);
      }
    };

    if (simulationId) {
      fetchMetadata(simulationId);
    } else {
      setLoading(true);
      api
        .listSimulations()
        .then(({ simulations }) => {
          if (simulations.length === 0) return null;
          const latestId = simulations[simulations.length - 1];
          fetchMetadata(latestId);
          return api.listAgents(latestId);
        })
        .then((result) => {
          if (result && result.agents) {
            setApiNames(result.agents.map((a) => a.name).sort());
          }
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [simulationId, storeNames.length]);

  const displayNames = storeNames.length > 0 ? storeNames : apiNames;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-teal-50 border border-teal-200 text-teal-700 dark:bg-teal-500/10 dark:border-teal-500/20 dark:text-teal-400 rounded-lg shadow-sm">
          <Bot className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Live agent panel — run a simulation from the Dashboard to see active agents.
          </p>
        </div>
      </div>

      {loading && Object.keys(agentMetadata).length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-teal-500" />
          Loading active agents…
        </div>
      ) : displayNames.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border/80 bg-secondary/5 p-16 text-center flex flex-col items-center justify-center gap-3 max-w-md mx-auto shadow-sm select-none my-8">
          <div className="p-3 rounded-full bg-teal-500/5 border border-teal-500/10 shadow-[0_0_15px_rgba(20,184,166,0.1)] text-teal-500/60 animate-pulse">
            <Bot className="h-8 w-8" />
          </div>
          <p className="text-muted-foreground text-sm max-w-xs leading-normal">
            {status === "running"
              ? "Live agents are spinning up. They will appear here as the simulation progresses…"
              : "No active simulation. Head back to the Dashboard to initiate an oil market simulation."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
          {displayNames.map((name) => (
            <AgentCard
              key={name}
              name={name}
              agentType={agentMetadata[name]?.agent_type}
              sector={agentMetadata[name]?.sector}
            />
          ))}
        </div>
      )}
    </div>
  );
}

