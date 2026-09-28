"use client";
import React from "react";
import { History, Newspaper } from "lucide-react";
import { useSimStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export interface OverlayHistory {
  /** 0-based position in the event log. */
  index: number;
  total: number;
  step: number;
  /** News headline of the focused event's step, if any. */
  headline: string | null;
}

/**
 * Slim top overlay. Live: step counter, run status, active news event.
 * History mode: scrub position + the focused step's headline.
 */
export function MapOverlay({ history }: { history?: OverlayHistory | null }) {
  const status = useSimStore((s) => s.status);
  const currentStep = useSimStore((s) => s.currentStep);
  const totalSteps = useSimStore((s) => s.totalSteps);
  const currentEvent = useSimStore((s) => s.currentEvent);

  const headline = history ? history.headline : currentEvent;

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 max-w-[85%]">
      {history ? (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-rose-300 bg-rose-50/95 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-400 backdrop-blur shadow-sm text-xs font-medium select-none shrink-0">
          <History className="h-3.5 w-3.5" />
          <span className="font-mono">
            Event {history.index + 1}/{history.total} · Step {history.step}
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-card/90 backdrop-blur shadow-sm text-xs font-medium select-none shrink-0">
          <span className="relative flex h-2 w-2">
            {status === "running" && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            )}
            <span
              className={cn(
                "relative inline-flex rounded-full h-2 w-2",
                status === "running" && "bg-emerald-500",
                status === "finished" && "bg-sky-500",
                status === "idle" && "bg-muted-foreground/40",
                status === "error" && "bg-red-500",
              )}
            />
          </span>
          {status === "idle" ? (
            <span className="text-muted-foreground">No active run</span>
          ) : (
            <span className="font-mono">
              Step {currentStep}/{totalSteps}
            </span>
          )}
        </div>
      )}

      {headline && (
        <div
          key={headline}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-amber-300 bg-amber-50/95 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300 backdrop-blur shadow-sm dark:shadow-[0_0_14px_rgba(245,158,11,0.25)] text-xs select-none min-w-0 animate-in fade-in slide-in-from-top-2 duration-500"
        >
          <Newspaper className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate" title={headline}>
            {headline}
          </span>
        </div>
      )}
    </div>
  );
}
