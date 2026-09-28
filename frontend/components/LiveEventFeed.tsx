"use client";
import React from "react";
import { useSimStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import type { AgentActionEvent, TradeEvent } from "@/types/simulation";
import { 
  Factory, Flame, Tag, Banknote, ArrowDownRight, 
  ArrowUpRight, ArrowLeftRight, Activity
} from "lucide-react";
import { cn } from "@/lib/utils";

const ACTION_CONFIG: Record<
  string, 
  { label: string; icon: React.ComponentType<{ className?: string }>; badgeClass: string; iconClass: string }
> = {
  produce: { label: "produce", icon: Factory, badgeClass: "bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-500/10 dark:text-sky-400 dark:border-sky-500/20", iconClass: "text-sky-600 dark:text-sky-400" },
  refine: { label: "refine", icon: Flame, badgeClass: "bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/20", iconClass: "text-purple-600 dark:text-purple-400" },
  list: { label: "list", icon: Tag, badgeClass: "bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20", iconClass: "text-amber-600 dark:text-amber-400" },
  borrow: { label: "borrow", icon: Banknote, badgeClass: "bg-orange-50 text-orange-700 border border-orange-200 dark:bg-orange-500/10 dark:text-orange-400 dark:border-orange-500/20", iconClass: "text-orange-600 dark:text-orange-400" },
  buy: { label: "buy", icon: ArrowDownRight, badgeClass: "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20", iconClass: "text-emerald-600 dark:text-emerald-400" },
  sell: { label: "sell", icon: ArrowUpRight, badgeClass: "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20", iconClass: "text-emerald-600 dark:text-emerald-400" },
};

export function LiveEventFeed() {
  const feed = useSimStore((s) => s.feed);

  return (
    <Card className="flex flex-col h-full border-border/80 shadow-md">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <div className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </div>
            Live Event Feed
          </CardTitle>
          <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider">
            Realtime Stream
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-72 px-4 py-3">
          {feed.length === 0 ? (
            <p className="text-xs text-muted-foreground py-8 text-center flex flex-col items-center justify-center gap-2 select-none">
              <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30 animate-pulse" />
              Waiting for events…
            </p>
          ) : (
            <ul className="space-y-2">
              {feed.map((e, i) => (
                <FeedRow key={i} event={e} />
              ))}
            </ul>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function FeedRow({ event }: { event: AgentActionEvent | TradeEvent }) {
  if (event.type === "trade") {
    return (
      <li className="text-xs flex items-center gap-2.5 p-2 rounded bg-secondary/15 hover:bg-secondary/25 border border-border/10 transition-colors select-none">
        <span className="font-mono text-muted-foreground/60 shrink-0 w-8 text-center text-[10px] bg-muted/30 py-0.5 rounded border border-border/20">
          #{event.step}
        </span>
        <Badge className="shrink-0 text-[10px] px-1.5 py-0.5 font-medium flex items-center gap-1 bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20">
          <ArrowLeftRight className="h-3 w-3" />
          trade
        </Badge>
        <span className="text-foreground/90 font-medium leading-tight truncate flex-1">{event.summary}</span>
      </li>
    );
  }
  
  const config = ACTION_CONFIG[event.action.toLowerCase()] || {
    label: event.action,
    icon: Activity,
    badgeClass: "bg-muted text-muted-foreground border border-border/40",
    iconClass: "text-muted-foreground/70"
  };
  const Icon = config.icon;

  return (
    <li className="text-xs flex items-center gap-2.5 p-2 rounded bg-secondary/15 hover:bg-secondary/25 border border-border/10 transition-colors select-none">
      <span className="font-mono text-muted-foreground/60 shrink-0 w-8 text-center text-[10px] bg-muted/30 py-0.5 rounded border border-border/20">
        #{event.step}
      </span>
      <Badge className={cn("shrink-0 text-[10px] px-1.5 py-0.5 font-medium flex items-center gap-1", config.badgeClass)}>
        <Icon className="h-3 w-3" />
        {config.label}
      </Badge>
      <span className="font-semibold text-foreground/90 shrink-0">{event.agent}</span>
      <span className="text-muted-foreground leading-tight truncate flex-1" title={event.summary}>
        {event.summary}
      </span>
    </li>
  );
}

