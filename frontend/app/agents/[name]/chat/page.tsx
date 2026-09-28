"use client";
import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useSimStore } from "@/lib/store";
import { ChatInterface } from "@/components/ChatInterface";
import { ArrowLeft, Loader2 } from "lucide-react";

function AgentChatContent() {
  const { name } = useParams<{ name: string }>();
  const searchParams = useSearchParams();
  const decodedName = decodeURIComponent(name);

  const urlSimId = searchParams.get("sim");
  const storeSimId = useSimStore((s) => s.simulationId);
  const storeStatus = useSimStore((s) => s.status);
  const [simId, setSimId] = useState<string | null>(urlSimId ?? storeSimId);
  const [loadingId, setLoadingId] = useState(false);
  const [agentMetadata, setAgentMetadata] = useState<{ agent_type: string; sector: string } | null>(null);

  useEffect(() => {
    if (storeSimId) setSimId(storeSimId);
  }, [storeSimId]);

  useEffect(() => {
    if (simId) return;
    setLoadingId(true);
    api.listSimulations()
      .then(({ simulations }) => {
        if (simulations.length > 0) setSimId(simulations[simulations.length - 1]);
      })
      .catch(() => {})
      .finally(() => setLoadingId(false));
  }, [simId]);

  useEffect(() => {
    if (!simId) return;
    api.listAgents(simId)
      .then((res) => {
        const found = res.agents.find((a) => a.name === decodedName);
        if (found) {
          setAgentMetadata({ agent_type: found.agent_type, sector: found.sector });
        }
      })
      .catch(() => {});
  }, [simId, decodedName]);

  const handleSend = async (message: string) => {
    if (!simId) throw new Error("No simulation available.");
    return api.agentChat(simId, decodedName, message);
  };

  return (
    <div className="h-[calc(100vh-48px)] flex flex-col gap-4 pb-2 min-h-0">
      <div className="flex items-center gap-3 shrink-0">
        <Link href={`/agents/${name}`} className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-xl font-semibold">Interview: {decodedName}</h1>
          <p className="text-sm text-muted-foreground">
            {simId ? (
              <span className="text-xs font-mono text-muted-foreground/70">{simId}</span>
            ) : (
              "No simulation selected."
            )}
          </p>
        </div>
      </div>

      {storeStatus === "running" ? (
        <p className="text-muted-foreground text-sm flex-1">Interview is only available after the simulation completes.</p>
      ) : loadingId ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 flex-1">
          <Loader2 className="h-4 w-4 animate-spin" />
          Looking for recent simulation…
        </div>
      ) : !simId ? (
        <p className="text-muted-foreground text-sm flex-1">Go to Dashboard and complete a simulation first.</p>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col">
          <ChatInterface
            onSend={handleSend}
            placeholder={`Ask ${decodedName} about their decisions…`}
            agentType={agentMetadata?.agent_type}
            stateKey={`chat:${simId}:${decodedName}`}
          />
        </div>
      )}
    </div>
  );
}

export default function AgentChatPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-8">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading…
      </div>
    }>
      <AgentChatContent />
    </Suspense>
  );
}
