"use client";
import { useEffect, useState } from "react";
import { useSimStore } from "@/lib/store";
import { api } from "@/lib/api";
import { ChatInterface } from "@/components/ChatInterface";
import { Loader2, Sparkles } from "lucide-react";

export default function ReportPage() {
  const storeSimId = useSimStore((s) => s.simulationId);
  const [simId, setSimId] = useState<string | null>(storeSimId);
  const [loadingList, setLoadingList] = useState(false);

  // Sync with store when a simulation completes while on this page
  useEffect(() => {
    if (storeSimId) setSimId(storeSimId);
  }, [storeSimId]);

  // If store has no ID, try to find the most recent simulation via API
  useEffect(() => {
    if (simId) return;
    setLoadingList(true);
    api.listSimulations()
      .then(({ simulations }) => {
        if (simulations.length > 0) {
          setSimId(simulations[simulations.length - 1]);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingList(false));
  }, [simId]);

  const handleSend = async (message: string) => {
    if (!simId) throw new Error("No simulation available. Run one first.");
    return api.reportChat(simId, message);
  };

  return (
    <div className="h-[calc(100vh-48px)] flex flex-col gap-4 pb-2 min-h-0">
      <div className="flex items-center gap-3 border-b border-border/40 pb-4 shrink-0">
        <div className="p-2 bg-indigo-50 border border-indigo-200 text-indigo-700 dark:bg-indigo-500/10 dark:border-indigo-500/20 dark:text-indigo-400 rounded-lg shadow-sm">
          <Sparkles className="h-5 w-5 animate-pulse" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Simulation Report</h1>
          <p className="text-sm text-muted-foreground flex items-center gap-2 mt-0.5 select-none">
            <span>Ask the Report Agent anything about the completed simulation.</span>
            {simId && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-muted/40 text-muted-foreground/80 border border-border/60 rounded">
                ID: {simId}
              </span>
            )}
          </p>
        </div>
      </div>

      {loadingList ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center flex-1">
          <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
          Looking for recent simulation run…
        </div>
      ) : !simId ? (
        <div className="rounded-lg border border-dashed border-border/80 bg-secondary/5 p-16 text-center flex flex-col items-center justify-center gap-3 max-w-md mx-auto shadow-sm select-none my-12">
          <div className="p-3 rounded-full bg-indigo-500/5 border border-indigo-500/10 shadow-[0_0_15px_rgba(99,102,241,0.1)] text-indigo-500/60 animate-pulse">
            <Sparkles className="h-8 w-8" />
          </div>
          <p className="text-muted-foreground text-sm max-w-xs leading-normal">
            No simulation results found. Head back to the Dashboard and run a simulation to compile a detailed analytical report.
          </p>
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col">
          <ChatInterface
            onSend={handleSend}
            placeholder="Ask about market dynamics, agent behavior, trends…"
            agentType="report"
            stateKey={`chat:${simId}:report`}
          />
        </div>
      )}
    </div>
  );
}

