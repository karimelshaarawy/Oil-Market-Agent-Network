"use client";
import React from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { Banknote, Factory, Flame, Landmark, Tag, TrendingUp, Users, Wrench, Bot, Activity } from "lucide-react";
import { useSimStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import type { ActionBadge, MapAgent } from "@/lib/mapModel";

export interface AgentNodeData extends Record<string, unknown> {
  agent: MapAgent;
  badge: ActionBadge | null;
  selected: boolean;
  /**
   * History mode: balance as of the scrub position (null = not yet known at
   * that point). Undefined = live mode, read the latest from the store.
   */
  balanceOverride?: number | null;
}

export type AgentNodeType = Node<AgentNodeData, "agent">;

/** Per-agent-type visuals — icons match AGENT_TYPE_CONFIG in AgentCard.tsx. */
const TYPE_CONFIG: Record<
  string,
  {
    icon: React.ComponentType<{ className?: string }>;
    bubble: string;
    glow: string;
  }
> = {
  firm: {
    icon: Wrench,
    bubble: "bg-sky-100 text-sky-700 border-sky-300 dark:bg-sky-500/15 dark:text-sky-400 dark:border-sky-500/40",
    glow: "shadow-[0_4px_20px_rgba(14,165,233,0.4)] dark:shadow-[0_0_26px_rgba(56,189,248,0.5)]",
  },
  refiner: {
    icon: Factory,
    bubble: "bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-500/15 dark:text-purple-400 dark:border-purple-500/40",
    glow: "shadow-[0_4px_20px_rgba(168,85,247,0.4)] dark:shadow-[0_0_26px_rgba(192,132,252,0.5)]",
  },
  consumer: {
    icon: Users,
    bubble: "bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-400 dark:border-emerald-500/40",
    glow: "shadow-[0_4px_20px_rgba(16,185,129,0.4)] dark:shadow-[0_0_26px_rgba(52,211,153,0.5)]",
  },
  speculator: {
    icon: TrendingUp,
    bubble: "bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-500/15 dark:text-amber-400 dark:border-amber-500/40",
    glow: "shadow-[0_4px_20px_rgba(245,158,11,0.4)] dark:shadow-[0_0_26px_rgba(251,191,36,0.5)]",
  },
  bank: {
    icon: Landmark,
    bubble: "bg-rose-100 text-rose-700 border-rose-300 dark:bg-rose-500/15 dark:text-rose-400 dark:border-rose-500/40",
    glow: "shadow-[0_4px_20px_rgba(244,63,94,0.4)] dark:shadow-[0_0_26px_rgba(251,113,133,0.5)]",
  },
  unknown: {
    icon: Bot,
    bubble: "bg-muted text-muted-foreground border-border",
    glow: "shadow-md",
  },
};

const BADGE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  produce: Factory,
  refine: Flame,
  list_good: Tag,
  borrow: Banknote,
  repay: Banknote,
};

export function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const { agent, badge, selected, balanceOverride } = data;
  const liveBalance = useSimStore((s) => s.balances[agent.name]);
  const balance = balanceOverride === undefined ? liveBalance : balanceOverride ?? undefined;
  const config = TYPE_CONFIG[agent.agentType] ?? TYPE_CONFIG.unknown;
  const Icon = config.icon;
  const active = badge !== null && !badge.dim;
  const BadgeIcon = badge ? BADGE_ICONS[badge.action] ?? Activity : Activity;

  return (
    <div className="relative w-24 flex flex-col items-center gap-1 select-none cursor-pointer group">
      {/* handles pinned to the icon bubble's vertical center */}
      <Handle type="target" position={Position.Left} style={{ top: 22 }} className="!opacity-0 !pointer-events-none" />
      <Handle type="source" position={Position.Right} style={{ top: 22 }} className="!opacity-0 !pointer-events-none" />

      {badge && (
        <div
          key={badge.id}
          className={cn(
            "absolute -top-8 left-1/2 whitespace-nowrap text-[10px] font-medium px-2 py-1 rounded-full border bg-popover/95 text-popover-foreground border-border shadow-md flex items-center gap-1 z-10 pointer-events-none",
            // Live badges fade themselves out; history badges stay until the
            // scrubber moves (dim = same-step context action).
            badge.persist ? "-translate-x-1/2" : "animate-map-badge",
            badge.dim && "opacity-50",
          )}
        >
          <BadgeIcon className="h-3 w-3 text-muted-foreground" />
          {badge.text}
        </div>
      )}

      <div
        className={cn(
          "p-2.5 rounded-full border-2 backdrop-blur transition-all duration-300",
          config.bubble,
          active
            ? cn(config.glow, "scale-110 animate-pulse")
            : "shadow-sm dark:shadow-none group-hover:scale-105 group-hover:shadow-md",
          selected && "ring-2 ring-primary/60 ring-offset-2 ring-offset-background",
        )}
      >
        <Icon className="h-5 w-5" />
      </div>

      <p className="text-[10px] font-semibold text-foreground leading-tight truncate max-w-full text-center">
        {agent.name}
      </p>
      <p
        className={cn(
          "text-[9px] font-mono font-semibold leading-none",
          balance !== undefined && balance < 0
            ? "text-red-600 dark:text-red-400"
            : "text-emerald-600 dark:text-emerald-400",
        )}
      >
        {balance !== undefined
          ? `$${balance.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
          : "—"}
      </p>
    </div>
  );
}
