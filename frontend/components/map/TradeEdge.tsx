"use client";
import React from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps, type Edge } from "@xyflow/react";
import { PULSE_TRAVEL_MS } from "@/lib/mapModel";

/**
 * live    — real-time trade: particle + label, then fades itself out via CSS.
 * focus   — history scrubber's selected event: bright, frozen, particle replays.
 * context — other events of the focused step: faint, frozen, no particle/label.
 * static  — idle snapshot view: hairline, no particle/label.
 */
export type TradeEdgeVariant = "live" | "focus" | "context" | "static";

export interface TradeEdgeData extends Record<string, unknown> {
  color: string;
  variant: TradeEdgeVariant;
  /** Midpoint label: the traded good (or "loan"/"repay" for financial edges). */
  label?: string;
}

export type TradeEdgeType = Edge<TradeEdgeData, "trade">;

/** How long a live edge stays visible after its trade before fading away. */
const EDGE_VISIBLE_MS = 5_000;

const EDGE_STYLE: Record<TradeEdgeVariant, (color: string) => React.CSSProperties> = {
  // Runs once per trade (edges remount on new trade ids) and freezes at
  // opacity 0 — the edge cleans itself up visually.
  live: (color) => ({
    stroke: color,
    strokeWidth: 1.5,
    animation: `map-edge-fade ${EDGE_VISIBLE_MS}ms ease-in forwards`,
  }),
  focus: (color) => ({ stroke: color, strokeWidth: 2, opacity: 0.92 }),
  context: (color) => ({ stroke: color, strokeWidth: 1.2, opacity: 0.28 }),
  static: (color) => ({ stroke: color, strokeWidth: 1, opacity: 0.18 }),
};

export function TradeEdge(props: EdgeProps<TradeEdgeType>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data } = props;
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });

  const color = data?.color ?? "#94a3b8";
  const variant = data?.variant ?? "static";
  const showParticle = variant === "live" || variant === "focus";
  const showLabel = Boolean(data?.label) && (variant === "live" || variant === "focus");

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={props.markerEnd} style={EDGE_STYLE[variant](color)} />
      {showParticle && (
        <g style={{ pointerEvents: "none" }}>
          {/* CSS offset-path animation runs once on mount and freezes at
              opacity 0, so no clock is needed to clean the particle up. */}
          <circle
            r={9}
            fill={color}
            style={
              {
                offsetPath: `path('${path}')`,
                offsetRotate: "0deg",
                animation: `map-pulse-travel ${PULSE_TRAVEL_MS}ms ease-in-out forwards`,
                "--pulse-opacity": 0.25,
              } as React.CSSProperties
            }
          />
          <circle
            r={4}
            fill={color}
            style={{
              offsetPath: `path('${path}')`,
              offsetRotate: "0deg",
              animation: `map-pulse-travel ${PULSE_TRAVEL_MS}ms ease-in-out forwards`,
              filter: `drop-shadow(0 0 6px ${color})`,
            }}
          />
        </g>
      )}
      {showLabel && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              color,
              // Live labels share the edge stroke's lifetime; focus labels stay.
              animation:
                variant === "live" ? `map-edge-fade ${EDGE_VISIBLE_MS}ms ease-in forwards` : undefined,
            }}
            className="absolute text-[9px] font-mono font-semibold px-1.5 py-0.5 rounded-full bg-card/85 border border-border/50 backdrop-blur-sm pointer-events-none select-none"
          >
            {data?.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
