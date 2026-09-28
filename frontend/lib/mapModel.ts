import type { AgentActionEvent, AgentTypeName, TradeEvent } from "@/types/simulation";

/** Category column order on the map: goods flow left → right. */
export type MapCategory = "upstream" | "downstream" | "consumer" | "financial" | "unknown";

/** Minimal agent descriptor the map needs to draw a node. */
export interface MapAgent {
  name: string;
  agentType: AgentTypeName | "unknown";
  category: MapCategory;
  sector?: string;
  region?: string;
}

/** One interaction edge derived from the live feed (trade or loan). */
export interface Pulse {
  id: string;
  /** Goods/cash flow direction: seller→buyer for trades, lender→borrower for loans. */
  source: string;
  target: string;
  kind: "trade" | "loan";
  good?: string;
  label: string;
  step: number;
}

/** Transient action badge shown above an acting node. */
export interface ActionBadge {
  id: string;
  action: string;
  text: string;
  /** History mode: badge stays until the scrubber moves (no auto-fade). */
  persist?: boolean;
  /** History mode: a same-step context action, rendered faint. */
  dim?: boolean;
}

/** Edges fade out via CSS seconds after their trade; this prunes the
 *  invisible leftovers from the graph once they're this many steps old. */
export const PULSE_MAX_AGE_STEPS = 2;
/** Duration of the travelling-particle animation (must match CSS usage). */
export const PULSE_TRAVEL_MS = 1_800;

/** Stroke/particle color per traded good (loans use the emerald "money" color). */
export const GOOD_COLORS: Record<string, string> = {
  crude_oil: "#f59e0b",
  refined_fuel: "#38bdf8",
  diesel: "#a78bfa",
};
export const LOAN_COLOR = "#34d399";
export const FALLBACK_GOOD_COLOR = "#94a3b8";

export function pulseColor(p: { kind: "trade" | "loan"; good?: string }): string {
  if (p.kind === "loan") return LOAN_COLOR;
  return GOOD_COLORS[p.good ?? ""] ?? FALLBACK_GOOD_COLOR;
}

// Stable per-event ids: feed event objects are immutable and identity-stable,
// so a memoized WeakMap lookup is pure (same event → same id, forever).
const eventIds = new WeakMap<object, number>();
let eventCounter = 0;

export function eventId(e: object): string {
  let id = eventIds.get(e);
  if (id === undefined) {
    id = ++eventCounter;
    eventIds.set(e, id);
  }
  return String(id);
}

export function pulseFromTrade(e: TradeEvent): Pulse {
  return {
    id: `pulse-${eventId(e)}`,
    source: e.seller,
    target: e.buyer,
    kind: "trade",
    good: e.good,
    label: `${e.qty} ${e.good} @ $${e.price.toFixed(2)}`,
    step: e.step,
  };
}

/** Loans are two-agent interactions: an approved loan disburses lender→borrower,
 * a repayment flows borrower→lender. (A request_loan application moves no money,
 * so it draws no edge until the bank approves it.) */
export function pulseFromLoan(e: AgentActionEvent): Pulse | null {
  if (e.action === "approve_loan" && e.to_agent) {
    return {
      id: `pulse-${eventId(e)}`,
      source: e.agent,
      target: e.to_agent,
      kind: "loan",
      good: undefined,
      label: e.amount !== undefined ? `loan $${e.amount.toFixed(0)}` : "loan",
      step: e.step,
    };
  }
  if (e.action === "repay" && e.to_agent) {
    return {
      id: `pulse-${eventId(e)}`,
      source: e.agent,
      target: e.to_agent,
      kind: "loan",
      good: undefined,
      label: e.amount !== undefined ? `repay $${e.amount.toFixed(0)}` : "repay",
      step: e.step,
    };
  }
  return null;
}

const COLUMN_X: Record<Exclude<MapCategory, "financial">, number> = {
  upstream: 40,
  downstream: 320,
  consumer: 600,
  unknown: 880,
};
const ROW_HEIGHT = 104;
const TOP_MARGIN = 70;
const FINANCIAL_SPACING = 200;

/**
 * Supply-chain layout: producers | refiners | consumers as columns,
 * banks/speculators in a row underneath.
 */
export function layoutPositions(agents: MapAgent[]): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  const columns: Record<string, MapAgent[]> = { upstream: [], downstream: [], consumer: [], unknown: [] };
  const financial: MapAgent[] = [];

  for (const a of agents) {
    if (a.category === "financial") financial.push(a);
    else columns[a.category in columns ? a.category : "unknown"].push(a);
  }

  let maxRows = 0;
  for (const [cat, members] of Object.entries(columns)) {
    members.forEach((a, i) => {
      positions[a.name] = {
        x: COLUMN_X[cat as Exclude<MapCategory, "financial">],
        y: TOP_MARGIN + i * ROW_HEIGHT,
      };
    });
    maxRows = Math.max(maxRows, members.length);
  }

  const financialY = TOP_MARGIN + Math.max(maxRows, 1) * ROW_HEIGHT + 60;
  const totalWidth = (financial.length - 1) * FINANCIAL_SPACING;
  const centerX = (COLUMN_X.upstream + COLUMN_X.consumer) / 2 + 80;
  financial.forEach((a, i) => {
    positions[a.name] = { x: centerX - totalWidth / 2 + i * FINANCIAL_SPACING, y: financialY };
  });

  return positions;
}
