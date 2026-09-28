"use client";
import React, { useMemo } from "react";
import Link from "next/link";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import { ArrowLeftRight, ArrowRight, MapPin, Wallet, X } from "lucide-react";
import { useSimStore } from "@/lib/store";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { MapAgent } from "@/lib/mapModel";

const EMPTY_HISTORY: { step: number; balance: number }[] = [];

interface Props {
  agent: MapAgent;
  onClose: () => void;
}

/** Right slide-over with live details for the clicked agent — the map keeps animating behind it. */
export function AgentSlideOver({ agent, onClose }: Props) {
  const balance = useSimStore((s) => s.balances[agent.name]);
  const balanceHistory = useSimStore((s) => s.balanceHistory[agent.name] ?? EMPTY_HISTORY);
  const feed = useSimStore((s) => s.feed);

  const recent = useMemo(
    () =>
      feed
        .filter((e) =>
          e.type === "trade" ? e.buyer === agent.name || e.seller === agent.name : e.agent === agent.name,
        )
        .slice(0, 30),
    [feed, agent.name],
  );

  return (
    <div className="absolute top-0 right-0 h-full w-72 z-20 border-l border-border bg-card/95 backdrop-blur-md shadow-xl flex flex-col animate-in slide-in-from-right duration-300 select-none">
      {/* header */}
      <div className="p-4 border-b border-border flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-sm text-foreground truncate">{agent.name}</p>
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            <Badge className="text-[9px] px-1.5 py-0.5 bg-muted/40 text-muted-foreground border border-border/50 capitalize">
              {agent.agentType}
            </Badge>
            {agent.region && (
              <Badge className="text-[9px] px-1.5 py-0.5 bg-muted/40 text-muted-foreground border border-border/50 flex items-center gap-1">
                <MapPin className="h-2.5 w-2.5" />
                {agent.region}
              </Badge>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* balance + sparkline */}
      <div className="p-4 border-b border-border space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground flex items-center gap-1.5">
            <Wallet className="h-3.5 w-3.5" />
            Balance
          </span>
          <span
            className={cn(
              "font-mono font-semibold",
              balance !== undefined && balance < 0
                ? "text-red-600 dark:text-red-400"
                : "text-emerald-600 dark:text-emerald-400",
            )}
          >
            {balance !== undefined
              ? `$${balance.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
              : "—"}
          </span>
        </div>
        {balanceHistory.length > 1 && (
          <div className="h-12 rounded bg-secondary/10 border border-border/20 p-0.5">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={balanceHistory}>
                <Line type="monotone" dataKey="balance" stroke="#2dd4bf" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* recent activity */}
      <div className="flex-1 min-h-0 flex flex-col">
        <p className="px-4 pt-3 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
          Recent activity
        </p>
        <ScrollArea className="flex-1 px-4 pb-3">
          {recent.length === 0 ? (
            <p className="text-xs text-muted-foreground py-6 text-center">No activity this run yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {recent.map((e, i) => (
                <li
                  key={i}
                  className="text-[11px] flex items-start gap-2 p-1.5 rounded bg-secondary/15 border border-border/10 leading-snug"
                >
                  <span className="font-mono text-muted-foreground/60 shrink-0 text-[9px] mt-0.5">#{e.step}</span>
                  {e.type === "trade" && (
                    <ArrowLeftRight className="h-3 w-3 shrink-0 mt-0.5 text-emerald-500/70" />
                  )}
                  <span className="text-foreground/85 min-w-0">{e.summary}</span>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </div>

      {/* footer link */}
      <div className="p-3 border-t border-border">
        <Link
          href={`/agents/${encodeURIComponent(agent.name)}`}
          className="flex items-center justify-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-primary transition-colors border border-border hover:border-primary/20 p-2 rounded bg-muted/20 hover:bg-primary/5 w-full"
        >
          Full details
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}
