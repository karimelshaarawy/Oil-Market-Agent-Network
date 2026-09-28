"use client";
import React, { useEffect } from "react";
import { ChevronLeft, ChevronRight, Radio } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SimStatus } from "@/types/simulation";

interface Props {
  /** Total events in the session log (> 0, the bar is hidden otherwise). */
  total: number;
  /** Current scrub position, or null when following live. */
  cursor: number | null;
  onChange: (cursor: number | null) => void;
  /** Summary text of the focused event (history mode only). */
  summary: string | null;
  status: SimStatus;
}

/** DVR-style transport bar docked at the bottom of the map canvas. */
export function MapTransportBar({ total, cursor, onChange, summary, status }: Props) {
  const atStart = cursor === 0;
  const live = cursor === null;
  const ahead = live ? 0 : total - 1 - cursor;

  const stepBack = () => onChange(live ? total - 1 : Math.max(0, cursor - 1));
  const stepForward = () => {
    if (live) return;
    // Stepping past the newest event returns to live following.
    onChange(cursor >= total - 1 ? null : cursor + 1);
  };

  // Arrow-key navigation; skip when focus is in a form control (the range
  // slider handles its own arrow keys natively).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      e.preventDefault();
      if (e.key === "ArrowLeft") onChange(cursor === null ? total - 1 : Math.max(0, cursor - 1));
      else if (cursor !== null) onChange(cursor >= total - 1 ? null : cursor + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cursor, total, onChange]);

  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-1 max-w-[92%]">
      {summary && (
        <div className="text-[11px] text-foreground/85 bg-card/90 backdrop-blur border border-border rounded-full px-3 py-1 shadow-sm max-w-full truncate select-none">
          {summary}
        </div>
      )}
      <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-full border border-border bg-card/95 backdrop-blur shadow-md select-none">
        <button
          onClick={stepBack}
          disabled={atStart}
          aria-label="Previous event"
          className="p-1 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 disabled:pointer-events-none transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button
          onClick={stepForward}
          disabled={live}
          aria-label="Next event"
          className="p-1 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 disabled:pointer-events-none transition-colors"
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        <input
          type="range"
          min={0}
          max={total - 1}
          value={live ? total - 1 : cursor}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label="Event history scrubber"
          className="w-36 md:w-56 accent-rose-500 cursor-pointer"
        />

        <span className="text-[10px] font-mono text-muted-foreground whitespace-nowrap">
          {live ? total : cursor + 1}/{total}
        </span>

        <button
          onClick={() => onChange(null)}
          disabled={live}
          aria-label="Return to live"
          className={cn(
            "flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-full border transition-colors",
            live
              ? "text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-500/30 bg-emerald-50 dark:bg-emerald-500/10 pointer-events-none"
              : "text-muted-foreground border-border hover:text-foreground hover:bg-muted",
          )}
        >
          <Radio className={cn("h-3 w-3", live && status === "running" && "animate-pulse")} />
          Live
          {ahead > 0 && (
            <span className="font-mono text-[9px] bg-rose-500/15 text-rose-600 dark:text-rose-400 px-1 rounded-full">
              +{ahead}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
