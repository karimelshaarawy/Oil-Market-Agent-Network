export type SimEvent =
  | SimulationStartEvent
  | StepStartEvent
  | AgentActionEvent
  | TradeEvent
  | StepCompleteEvent
  | SimulationCompleteEvent
  | HeartbeatEvent
  | StoppedEvent
  | ErrorEvent;

export interface SimulationStartEvent {
  type: "simulation_start";
  simulation_id: string;
}

export interface StepStartEvent {
  type: "step_start";
  step: number;
  event_text: string | null;
}

export interface AgentActionEvent {
  type: "agent_action";
  step: number;
  agent: string;
  agent_id: number;
  action: string;
  good?: string;
  qty?: number;
  price?: number;
  amount?: number;
  balance?: number;
  /** Counterparty for loan actions: borrower on "approve_loan"/"deny_loan"
   * (to_agent) and bank on "request_loan" (to_agent); lender on "repay" (to_agent). */
  from_agent?: string;
  to_agent?: string;
  summary: string;
}

export interface TradeEvent {
  type: "trade";
  step: number;
  buyer: string;
  buyer_id: number;
  seller: string;
  seller_id: number;
  good: string;
  qty: number;
  price: number;
  total: number;
  buyer_balance?: number;
  seller_balance?: number;
  summary: string;
}

export interface StepCompleteEvent {
  type: "step_complete";
  step: number;
  balances: Record<string, number>;
  prices: Record<string, number>;
}

export interface SimulationCompleteEvent {
  type: "simulation_complete";
  simulation_id: string;
  agent_names: string[];
}

export interface HeartbeatEvent {
  type: "heartbeat";
}

export interface StoppedEvent {
  type: "stopped";
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

// REST API shapes
export interface Agent {
  agent_id: number;
  name: string;
  agent_type: string;
  sector: string;
  balance: number;
}

export interface PricePoint {
  good_name: string;
  price: number;
  quantity: number;
  timestamp: number;
}

export interface Transaction {
  buyer_id: number;
  buyer: string;
  seller_id: number;
  seller: string;
  good_name: string;
  price: number;
  quantity: number;
  timestamp: number;
}

export interface BalancePoint {
  name: string;
  step: number;
  running_balance: number;
}

export interface SimSnapshot {
  agents: Agent[];
  price_history: PricePoint[];
  transactions: Transaction[];
  balance_history: BalancePoint[];
}

export interface TraceEntry {
  timestamp: number;
  action: string;
  info: string;
}

export interface LedgerEntry {
  step: number;
  category: string;
  amount: number;
  description: string;
}

export interface BalanceStep {
  step: number;
  balance: number;
}

export interface InventoryItem {
  name: string;
  quantity: number;
  avg_unit_cost: number;
}

export interface AgentHistory {
  agent_name: string;
  traces: TraceEntry[];
  ledger: LedgerEntry[];
  balance_steps: BalanceStep[];
  inventory: InventoryItem[];
}

export type SimStatus = "idle" | "running" | "finished" | "error";

/** The five agent behaviours the simulation backend understands. */
export type AgentTypeName = "firm" | "refiner" | "consumer" | "speculator" | "bank";

/** Filter category a profile belongs to (derived from the agent type). */
export type AgentCategory = "upstream" | "downstream" | "financial" | "consumer";

/** A per-step demand requirement for a consumer agent. */
export interface ConsumptionNeed {
  good_name: string;
  quantity_per_step: number;
  revenue_per_unit: number;
  reference_price: number;
  price_pass_through: number;
  shortage_penalty_per_unit: number;
  reserve_target_steps: number;
}

/**
 * A user-editable agent profile. Mirrors the JSON shape the backend reads in
 * econ/data/agents/oil_agents.json. Only name/agent_type/sector/initial_capital
 * are required by the backend; the rest carry safe defaults.
 */
export interface AgentProfile {
  name: string;
  category: AgentCategory;
  agent_type: AgentTypeName;
  sector: string;
  region: string;
  initial_capital: number;
  risk_tolerance: number;
  persona: string;
  produces: string[];
  inputs?: string[];
  unit_costs?: Record<string, number>;
  consumption_needs?: ConsumptionNeed[];
}

export interface SimParams {
  n_steps: number;
  semaphore: number;
  max_iteration: number;
  rag_enabled: boolean;
  rag_reset_on_start: boolean;
  include_upstream: boolean;
  include_downstream: boolean;
  include_financial: boolean;
  include_consumer: boolean;
  use_generated_events: boolean;
  use_live_news: boolean;
  /** Days of recent news to look back over when use_live_news is enabled. */
  news_lookback_days: number;
  seed_context_text?: string;
  /** User-defined agent roster; when non-empty it replaces the default file roster. */
  custom_agents: AgentProfile[];
}
