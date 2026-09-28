import { create } from "zustand";
import type {
  AgentActionEvent,
  SimParams,
  SimStatus,
  TradeEvent,
} from "@/types/simulation";
import { cloneDefaultAgents } from "@/lib/defaultAgents";

export const DEFAULT_SIM_PARAMS: SimParams = {
  n_steps: 8,
  semaphore: 3,
  max_iteration: 3,
  rag_enabled: true,
  rag_reset_on_start: true,
  include_upstream: true,
  include_downstream: true,
  include_financial: true,
  include_consumer: true,
  use_generated_events: true,
  use_live_news: false,
  news_lookback_days: 7,
  seed_context_text: "",
  custom_agents: cloneDefaultAgents(),
};

export interface LiveAgentState {
  lastAction: string;
  step: number;
}

export interface SimStore {
  status: SimStatus;
  simulationId: string | null;
  currentStep: number;
  totalSteps: number;
  currentEvent: string | null;

  // balances[agentName] = latest balance
  balances: Record<string, number>;
  // balanceHistory[agentName] = [{step, balance}, ...]
  balanceHistory: Record<string, Array<{ step: number; balance: number }>>;

  // prices[goodName] = latest price
  prices: Record<string, number>;
  // priceHistory[goodName] = [{step, price}, ...]
  priceHistory: Record<string, Array<{ step: number; price: number }>>;

  // per-agent live status
  agentStates: Record<string, LiveAgentState>;

  // live feed of recent events (capped at 200, newest first)
  feed: Array<AgentActionEvent | TradeEvent>;

  // full chronological event history for this session (uncapped, oldest first);
  // drives the map's replay scrubber
  eventLog: Array<AgentActionEvent | TradeEvent>;
  // stepEvents[step] = news headline that fired at that step (null = no event)
  stepEvents: Record<number, string | null>;

  agentNames: string[];

  // control board params (persisted across navigation)
  params: SimParams;
  setSimParams: (updater: (p: SimParams) => SimParams) => void;

  // actions
  setStatus: (s: SimStatus) => void;
  setTotalSteps: (n: number) => void;
  applyStepStart: (step: number, eventText: string | null) => void;
  applyAgentAction: (e: AgentActionEvent) => void;
  applyTrade: (e: TradeEvent) => void;
  applyStepComplete: (step: number, balances: Record<string, number>, prices: Record<string, number>) => void;
  applyStart: (simulationId: string) => void;
  applyComplete: (simulationId: string, agentNames: string[]) => void;
  reset: () => void;
  beginRun: (totalSteps: number) => void;
}

const INITIAL: Omit<SimStore, "setStatus" | "setTotalSteps" | "setSimParams" | "applyStart" | "applyStepStart" | "applyAgentAction" | "applyTrade" | "applyStepComplete" | "applyComplete" | "reset" | "beginRun"> = {
  status: "idle",
  simulationId: null,
  currentStep: 0,
  totalSteps: 8,
  currentEvent: null,
  balances: {},
  balanceHistory: {},
  prices: {},
  priceHistory: {},
  agentStates: {},
  feed: [],
  eventLog: [],
  stepEvents: {},
  agentNames: [],
  params: DEFAULT_SIM_PARAMS,
};

export const useSimStore = create<SimStore>((set) => ({
  ...INITIAL,

  setStatus: (s) => set({ status: s }),
  setTotalSteps: (n) => set({ totalSteps: n }),
  setSimParams: (updater) => set((state) => ({ params: updater(state.params) })),

  reset: () => set((state) => ({ ...INITIAL, params: state.params })),

  // Atomic transition for starting a new run: clears prior data, flips
  // status to "running" and sets totalSteps in a single notification so
  // subscribers (and recharts mount cycles) only see one transition.
  beginRun: (totalSteps) =>
    set((state) => ({
      ...INITIAL,
      params: state.params,
      status: "running",
      totalSteps,
    })),

  applyStepStart: (step, eventText) =>
    set((state) => ({
      currentStep: step,
      currentEvent: eventText,
      stepEvents: { ...state.stepEvents, [step]: eventText },
    })),

  applyAgentAction: (e) =>
    set((state) => {
      const nameSet = new Set(state.agentNames);
      nameSet.add(e.agent);
      const newBalances = e.balance !== undefined
        ? { ...state.balances, [e.agent]: e.balance }
        : state.balances;
      const newBalHist = e.balance !== undefined
        ? {
            ...state.balanceHistory,
            [e.agent]: [
              ...(state.balanceHistory[e.agent] ?? []),
              { step: e.step, balance: e.balance },
            ],
          }
        : state.balanceHistory;
      return {
        agentStates: {
          ...state.agentStates,
          [e.agent]: { lastAction: e.summary, step: e.step },
        },
        balances: newBalances,
        balanceHistory: newBalHist,
        feed: [e, ...state.feed].slice(0, 200),
        eventLog: [...state.eventLog, e],
        agentNames: nameSet.size !== state.agentNames.length
          ? Array.from(nameSet).sort()
          : state.agentNames,
      };
    }),

  applyTrade: (e) =>
    set((state) => {
      const tradeLabel = `Bought ${e.qty} ${e.good} @ $${e.price}`;
      const sellLabel  = `Sold ${e.qty} ${e.good} @ $${e.price}`;
      const newStates = {
        ...state.agentStates,
        [e.buyer]:  { lastAction: tradeLabel, step: e.step },
        [e.seller]: { lastAction: sellLabel,  step: e.step },
      };
      const newBalances = { ...state.balances };
      const newBalHist  = { ...state.balanceHistory };
      if (e.buyer_balance !== undefined) {
        newBalances[e.buyer] = e.buyer_balance;
        newBalHist[e.buyer]  = [...(newBalHist[e.buyer] ?? []), { step: e.step, balance: e.buyer_balance }];
      }
      if (e.seller_balance !== undefined) {
        newBalances[e.seller] = e.seller_balance;
        newBalHist[e.seller]  = [...(newBalHist[e.seller] ?? []), { step: e.step, balance: e.seller_balance }];
      }
      const nameSet = new Set(state.agentNames);
      nameSet.add(e.buyer);
      nameSet.add(e.seller);
      return {
        agentStates: newStates,
        balances: newBalances,
        balanceHistory: newBalHist,
        feed: [e, ...state.feed].slice(0, 200),
        eventLog: [...state.eventLog, e],
        agentNames: nameSet.size !== state.agentNames.length
          ? Array.from(nameSet).sort()
          : state.agentNames,
      };
    }),

  applyStepComplete: (step, balances, prices) =>
    set((state) => {
      const newBalHist = { ...state.balanceHistory };
      for (const [name, bal] of Object.entries(balances)) {
        newBalHist[name] = [...(newBalHist[name] ?? []), { step, balance: bal }];
      }
      const newPriceHist = { ...state.priceHistory };
      for (const [good, price] of Object.entries(prices)) {
        newPriceHist[good] = [...(newPriceHist[good] ?? []), { step, price }];
      }
      // step_complete carries every agent — use it as the authoritative name list
      const allNames = Object.keys(balances).sort();
      return {
        balances,
        prices,
        balanceHistory: newBalHist,
        priceHistory: newPriceHist,
        agentNames: allNames,
      };
    }),

  applyStart: (simulationId) => set({ simulationId }),

  applyComplete: (simulationId, agentNames) =>
    set((state) => ({
      status: "finished",
      simulationId,
      // simulation_complete list is authoritative; fall back to whatever we already have
      agentNames: agentNames.length > 0 ? agentNames.sort() : state.agentNames,
    })),
}));
