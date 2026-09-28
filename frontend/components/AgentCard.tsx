"use client";
import React from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useSimStore } from "@/lib/store";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import { MessageSquare, Droplet, Factory, TrendingUp, Users, Wallet, Activity, Bot, Landmark, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";

export const AGENT_TYPE_CONFIG: Record<
  string, 
  { color: string; icon: React.ComponentType<{ className?: string }> }
> = {
  firm: { color: "bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-500/10 dark:text-sky-400 dark:border-sky-500/20", icon: Wrench },
  refiner: { color: "bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20", icon: Factory },
  speculator: { color: "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20", icon: TrendingUp },
  consumer: { color: "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20", icon: Users },
  bank: { color: "bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/20", icon: Landmark },
};

const SECTOR_CONFIG: Record<
  string, 
  { color: string; icon: React.ComponentType<{ className?: string }> }
> = {
  upstream: { color: "bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-500/10 dark:text-sky-400 dark:border-sky-500/20", icon: Droplet },
  downstream: { color: "bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20", icon: Factory },
  financial: { color: "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20", icon: TrendingUp },
  consumer: { color: "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20", icon: Users },
};

const EMPTY_HISTORY: { step: number; balance: number }[] = [];

interface Props {
  name: string;
  agentType?: string;
  sector?: string;
}

export function AgentCard({ name, agentType, sector }: Props) {
  const agentState = useSimStore((s) => s.agentStates[name]);
  const balance = useSimStore((s) => s.balances[name]);
  const balanceHistory = useSimStore((s) => s.balanceHistory[name] ?? EMPTY_HISTORY);
  const simulationId = useSimStore((s) => s.simulationId);
  const status = useSimStore((s) => s.status);

  const typeConfig = AGENT_TYPE_CONFIG[agentType?.toLowerCase() ?? ""] || {
    color: "bg-muted/40 border border-border/50 text-muted-foreground/70",
    icon: Bot
  };
  const AgentIcon = typeConfig.icon;

  const sectorConfig = SECTOR_CONFIG[sector?.toLowerCase() ?? ""] || {
    color: "bg-muted/30 text-muted-foreground border border-border/40",
    icon: Bot
  };
  const SectorIcon = sectorConfig.icon;

  return (
    <Card className="hover:border-primary/30 hover:shadow-md transition-all duration-300 group bg-card select-none">
      <CardContent className="p-4 space-y-3.5">
        {/* header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0 flex-1">
            <div className={cn("p-1.5 rounded shrink-0 transition-all duration-300 group-hover:scale-105 shadow-sm", typeConfig.color)}>
              <AgentIcon className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1">
              <Link href={`/agents/${encodeURIComponent(name)}`} className="font-semibold text-xs text-foreground/95 hover:text-primary hover:underline truncate block transition-colors leading-tight">
                {name}
              </Link>
              <p className="text-[10px] text-muted-foreground truncate mt-0.5 leading-normal">{agentType}</p>
            </div>
          </div>
          {sector && (
            <Badge className={cn("text-[9px] px-1.5 py-0.5 shrink-0 flex items-center gap-1 font-medium rounded select-none shadow-sm", sectorConfig.color)}>
              <SectorIcon className="h-2.5 w-2.5" />
              {sector}
            </Badge>
          )}
        </div>

        {/* sparkline */}
        {balanceHistory.length > 1 ? (
          <div className="h-10 relative overflow-hidden rounded bg-secondary/10 border border-border/10 p-0.5">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={balanceHistory}>
                <Line type="monotone" dataKey="balance" stroke="#2dd4bf" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-10 bg-muted/20 border border-border/10 rounded flex items-center justify-center">
            <span className="text-[9px] text-muted-foreground/60">No history logged</span>
          </div>
        )}

        {/* balance */}
        <div className="flex items-center justify-between text-xs border-t border-border/30 pt-2.5">
          <span className="text-muted-foreground flex items-center gap-1">
            <Wallet className="h-3.5 w-3.5 text-muted-foreground/60" />
            Balance
          </span>
          <span className={cn("font-mono font-semibold", balance !== undefined && balance < 0 ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400")}>
            {balance !== undefined ? `$${balance.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "—"}
          </span>
        </div>

        {/* last action */}
        {agentState && (
          <div className="text-[10px] text-muted-foreground bg-muted/15 border border-border/20 p-2 rounded flex items-start gap-2 leading-relaxed">
            <Activity className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40 mt-0.5" />
            <span className="truncate flex-1" title={agentState.lastAction}>
              <span className="font-semibold text-foreground/80 font-mono">#{agentState.step}</span>: {agentState.lastAction}
            </span>
          </div>
        )}

        {/* interview button — only shown post-simulation */}
        {simulationId && status !== "running" && (
          <Link
            href={`/agents/${encodeURIComponent(name)}/chat?sim=${simulationId}`}
            className="flex items-center justify-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-primary transition-all duration-200 border border-border hover:border-primary/20 p-1.5 rounded bg-muted/20 hover:bg-primary/5 w-full select-none"
          >
            <MessageSquare className="h-3.5 w-3.5 group-hover:animate-bounce" />
            Interview Agent
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

