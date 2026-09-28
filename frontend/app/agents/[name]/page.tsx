"use client";
import React, { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AgentHistory } from "@/types/simulation";
import { useSimStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { 
  ArrowLeft, MessageSquare, Loader2, Bot, LineChart as ChartIcon, 
  Package, History as HistoryIcon, Receipt, Coins, Calendar, Activity
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AGENT_TYPE_CONFIG } from "@/components/AgentCard";

export default function AgentDetailPage() {
  const { name } = useParams<{ name: string }>();
  const decodedName = decodeURIComponent(name);
  const storeSimId = useSimStore((s) => s.simulationId);
  const storeStatus = useSimStore((s) => s.status);
  const currentStep = useSimStore((s) => s.currentStep);
  const [simulationId, setSimulationId] = useState<string | null>(storeSimId);
  const [history, setHistory] = useState<AgentHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState(false);
  const [agentMetadata, setAgentMetadata] = useState<{ agent_type: string; sector: string } | null>(null);

  // Sync with store (e.g. simulation completes while on this page)
  useEffect(() => {
    if (storeSimId) setSimulationId(storeSimId);
  }, [storeSimId]);

  // Fallback: load latest simulation from API if store has no ID
  useEffect(() => {
    if (simulationId) return;
    setLoadingId(true);
    api.listSimulations()
      .then(({ simulations }) => {
        if (simulations.length > 0) setSimulationId(simulations[simulations.length - 1]);
      })
      .catch(() => {})
      .finally(() => setLoadingId(false));
  }, [simulationId]);

  useEffect(() => {
    if (!simulationId) return;
    // Don't flash null on live re-fetches — keep showing stale data while loading
    if (storeStatus !== "running") setHistory(null);
    setError(null);
    api.agentHistory(simulationId, decodedName)
      .then(setHistory)
      .catch((e) => setError(String(e)));
  // currentStep triggers a re-fetch after each step completes during a live run
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simulationId, decodedName, storeStatus === "running" ? currentStep : 0]);

  useEffect(() => {
    if (!simulationId) return;
    api.listAgents(simulationId)
      .then((res) => {
        const found = res.agents.find((a) => a.name === decodedName);
        if (found) {
          setAgentMetadata({ agent_type: found.agent_type, sector: found.sector });
        }
      })
      .catch(() => {});
  }, [simulationId, decodedName]);

  const typeConfig = AGENT_TYPE_CONFIG[agentMetadata?.agent_type?.toLowerCase() ?? ""] || {
    color: "bg-muted/40 border border-border/50 text-muted-foreground/70",
    icon: Bot
  };
  const AgentIcon = typeConfig.icon;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-border/40 pb-4">
        <div className="flex items-center gap-3">
          <Link href="/agents" className="p-2 border border-border/80 rounded-lg bg-secondary/30 text-muted-foreground hover:text-foreground transition-all hover:scale-105 shadow-sm">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex items-center gap-2.5">
            <div className={cn("p-2 rounded-lg shadow-sm shrink-0 transition-colors duration-300", typeConfig.color)}>
              <AgentIcon className={cn("h-5 w-5", storeStatus === "running" && "animate-pulse")} />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-foreground flex items-center gap-2 leading-none">
                {decodedName}
                {agentMetadata && (
                  <Badge variant="outline" className="text-[10px] font-mono px-2 py-0.5 capitalize bg-background/50 border-border/60 text-muted-foreground select-none shrink-0 font-medium">
                    {agentMetadata.agent_type}
                  </Badge>
                )}
              </h1>
              <p className="text-sm text-muted-foreground flex items-center gap-2 mt-1">
                Agent profile details
                {storeStatus === "running" && (
                  <span className="inline-flex items-center gap-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200 dark:bg-green-500/15 dark:text-green-400 dark:border-green-500/25 select-none">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                    Live · step {currentStep}
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
        {simulationId && storeStatus !== "running" && (
          <Link
            href={`/agents/${encodeURIComponent(decodedName)}/chat?sim=${simulationId}`}
            className="flex items-center gap-1.5 px-3 py-2 font-medium text-xs text-muted-foreground hover:text-primary transition-all duration-200 border border-border hover:border-primary/20 rounded bg-muted/20 hover:bg-primary/5 shadow-sm select-none"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Interview Agent
          </Link>
        )}
      </div>

      {loadingId || (!simulationId && !error) ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-teal-500" />
          {loadingId ? "Looking for recent simulation run…" : "Loading data…"}
        </div>
      ) : !simulationId ? (
        <div className="rounded-lg border border-dashed border-border p-16 text-center select-none max-w-md mx-auto">
          <p className="text-muted-foreground text-sm">No active simulation found. Go to Dashboard to initiate one.</p>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-8 text-center max-w-md mx-auto">
          <p className="text-destructive text-sm font-medium">{error}</p>
        </div>
      ) : !history ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin text-teal-500" />
          Loading agent history details…
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Balance over time */}
          <Card className="shadow-md border-border/80">
            <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
              <CardTitle className="text-xs font-semibold flex items-center gap-2">
                <ChartIcon className="h-4 w-4 text-sky-600 dark:text-sky-400" />
                Balance over Time
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {history.balance_steps.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center gap-2 select-none">
                  <Coins className="h-8 w-8 text-muted-foreground/30 animate-pulse" />
                  <p className="text-xs text-muted-foreground">No balance timeline data.</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={history.balance_steps}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="step" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} width={56} />
                    <Tooltip 
                      contentStyle={{ 
                        background: "var(--card)", 
                        border: "1px solid var(--border)", 
                        borderRadius: "8px", 
                        fontSize: "11px",
                        boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.15)"
                      }}
                      itemStyle={{ color: "var(--foreground)" }}
                      labelStyle={{ color: "var(--muted-foreground)", fontWeight: 600 }}
                      cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
                    />
                    <Line type="monotone" dataKey="balance" stroke="#38bdf8" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Inventory */}
          <Card className="shadow-md border-border/80">
            <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
              <CardTitle className="text-xs font-semibold flex items-center gap-2">
                <Package className="h-4 w-4 text-teal-600 dark:text-teal-400" />
                Current Inventory
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {history.inventory.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center gap-2 select-none">
                  <Package className="h-8 w-8 text-muted-foreground/30 animate-pulse" />
                  <p className="text-xs text-muted-foreground">No inventory holdings logged.</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={history.inventory} layout="vertical" margin={{ left: 80, right: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "var(--foreground)" }} width={80} />
                    <Tooltip 
                      contentStyle={{ 
                        background: "var(--card)", 
                        border: "1px solid var(--border)", 
                        borderRadius: "8px", 
                        fontSize: "11px",
                        boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.15)"
                      }}
                      itemStyle={{ color: "var(--foreground)" }}
                      labelStyle={{ color: "var(--muted-foreground)", fontWeight: 600 }}
                      cursor={{ fill: "var(--muted)", opacity: 0.15 }}
                    />
                    <Bar dataKey="quantity" fill="#2dd4bf" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Action traces */}
          <Card className="shadow-md border-border/80 md:col-span-2">
            <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
              <CardTitle className="text-xs font-semibold flex items-center gap-2">
                <HistoryIcon className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                Action History Traces
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-72 px-4 pb-3 pt-2">
                {history.traces.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center gap-2 select-none">
                    <Activity className="h-8 w-8 text-muted-foreground/30 animate-pulse" />
                    <p className="text-xs text-muted-foreground">No action history recorded.</p>
                  </div>
                ) : (
                  <ul className="space-y-2 pt-2">
                    {history.traces.map((t, i) => (
                      <li key={i} className="text-xs flex gap-3 p-2 rounded bg-secondary/10 border border-border/10">
                        <Badge variant="outline" className="text-[10px] shrink-0 font-mono h-5 flex items-center bg-muted/40">
                          #{t.timestamp}
                        </Badge>
                        <div className="min-w-0 flex-1">
                          <span className="font-semibold text-foreground/90">{t.action}</span>
                          {t.info && <p className="text-muted-foreground mt-1 whitespace-pre-wrap leading-relaxed text-[11px] font-mono bg-background/50 p-1.5 rounded border border-border/20">{t.info}</p>}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Ledger */}
          <Card className="shadow-md border-border/80 md:col-span-2">
            <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
              <CardTitle className="text-xs font-semibold flex items-center gap-2">
                <Receipt className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                Financial Ledger Ledger
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-64 px-4 pb-3 pt-2">
                {history.ledger.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center gap-2 select-none">
                    <Receipt className="h-8 w-8 text-muted-foreground/30 animate-pulse" />
                    <p className="text-xs text-muted-foreground">No ledger transactions.</p>
                  </div>
                ) : (
                  <table className="w-full text-xs select-none">
                    <thead>
                      <tr className="text-muted-foreground border-b border-border">
                        <th className="text-left py-2 font-semibold">Step</th>
                        <th className="text-left py-2 font-semibold">Category</th>
                        <th className="text-right py-2 font-semibold">Amount</th>
                        <th className="text-left py-2 pl-4 font-semibold">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.ledger.map((l, i) => (
                        <tr key={i} className="border-b border-border/40 hover:bg-secondary/15 transition-colors">
                          <td className="py-2.5 font-mono font-medium">#{l.step}</td>
                          <td className="py-2.5">
                            <span className="px-1.5 py-0.5 rounded bg-muted/40 text-[10px] font-medium border border-border/30">
                              {l.category}
                            </span>
                          </td>
                          <td className={`py-2.5 text-right font-mono font-semibold ${l.amount < 0 ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                            {l.amount < 0 ? "-" : "+"}${Math.abs(l.amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </td>
                          <td className="py-2.5 pl-4 text-muted-foreground leading-normal">{l.description}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

