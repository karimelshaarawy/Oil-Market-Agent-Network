import type {
  AgentCategory,
  AgentProfile,
  AgentTypeName,
  ConsumptionNeed,
} from "@/types/simulation";

/** Goods the oil-market simulation knows about (free text still allowed). */
export const KNOWN_GOODS = ["crude_oil", "refined_fuel", "diesel"] as const;

/** Common regions (free text still allowed). Same region = 0 transport cost. */
export const REGIONS = ["MiddleEast", "Texas", "Europe", "NewYork"] as const;

/** Every selectable agent type, in display order. */
export const AGENT_TYPES: AgentTypeName[] = [
  "firm",
  "refiner",
  "consumer",
  "speculator",
  "bank",
];

/** The filter category each agent type maps to. */
export const CATEGORY_BY_TYPE: Record<AgentTypeName, AgentCategory> = {
  firm: "upstream",
  refiner: "downstream",
  consumer: "consumer",
  speculator: "financial",
  bank: "financial",
};

/** Human-friendly label per type for dropdowns. */
export const AGENT_TYPE_LABEL: Record<AgentTypeName, string> = {
  firm: "Producer (firm)",
  refiner: "Refiner",
  consumer: "Consumer",
  speculator: "Speculator",
  bank: "Bank",
};

function defaultConsumptionNeed(): ConsumptionNeed {
  return {
    good_name: "refined_fuel",
    quantity_per_step: 40,
    revenue_per_unit: 85.0,
    reference_price: 45.0,
    price_pass_through: 0.6,
    shortage_penalty_per_unit: 100.0,
    reserve_target_steps: 2,
  };
}

/**
 * Build a sensible pre-filled agent for a newly added row (or when the user
 * switches an existing agent's type). Derives category/sector and the
 * type-specific fields; shared fields (name/region/capital/risk) are passed in
 * so a type switch keeps what the user already entered.
 */
export function makeDefaultAgent(
  type: AgentTypeName,
  overrides: Partial<AgentProfile> = {},
): AgentProfile {
  const base: AgentProfile = {
    name: "NewAgent",
    category: CATEGORY_BY_TYPE[type],
    agent_type: type,
    sector: "energy_upstream",
    region: "MiddleEast",
    initial_capital: 15000,
    risk_tolerance: 0.5,
    persona: "",
    produces: [],
  };

  switch (type) {
    case "firm":
      base.sector = "energy_upstream";
      base.produces = ["crude_oil"];
      base.unit_costs = { crude_oil: 10 };
      break;
    case "refiner":
      base.sector = "energy_downstream";
      base.inputs = ["crude_oil"];
      base.produces = ["refined_fuel"];
      break;
    case "speculator":
      base.sector = "commodity_trading";
      base.region = "NewYork";
      base.risk_tolerance = 0.8;
      base.produces = [];
      break;
    case "bank":
      base.sector = "finance";
      base.region = "NewYork";
      base.initial_capital = 50000;
      base.risk_tolerance = 0.35;
      base.produces = [];
      break;
    case "consumer":
      base.sector = "transportation";
      base.region = "Europe";
      base.initial_capital = 25000;
      base.risk_tolerance = 0.4;
      base.produces = [];
      base.consumption_needs = [defaultConsumptionNeed()];
      break;
  }

  return { ...base, ...overrides, category: CATEGORY_BY_TYPE[type], agent_type: type };
}

export { defaultConsumptionNeed };

/**
 * The 11-agent default roster, transcribed from
 * econ/data/agents/oil_agents.json. Used to pre-seed the builder.
 */
export const DEFAULT_AGENTS: AgentProfile[] = [
  {
    name: "ArabianPetroleum",
    category: "upstream",
    agent_type: "firm",
    sector: "energy_upstream",
    region: "MiddleEast",
    initial_capital: 15000.0,
    risk_tolerance: 0.65,
    persona:
      "A state-backed upstream crude oil producer with vast reserves and very low extraction costs (~$8/barrel equivalent). Controls output strategically to defend price floors. Will cut production when global prices fall below a target level and flood the market to punish rival producers who overproduce. Monitors price history closely and always lists crude_oil immediately after producing it.",
    produces: ["crude_oil"],
    unit_costs: { crude_oil: 8.0 },
  },
  {
    name: "ShaleProducer",
    category: "upstream",
    agent_type: "firm",
    sector: "energy_upstream",
    region: "Texas",
    initial_capital: 7000.0,
    risk_tolerance: 0.8,
    persona:
      "An independent US shale oil producer with higher break-even costs (~$40/barrel equivalent). Carries significant debt and must produce continuously to service it. Ramps output up aggressively when crude prices are high. Highly vulnerable to price drops — will cut production sharply and may need to borrow if margins turn negative for multiple steps.",
    produces: ["crude_oil"],
    unit_costs: { crude_oil: 40.0 },
  },
  {
    name: "MegaRefinery",
    category: "downstream",
    agent_type: "refiner",
    sector: "energy_downstream",
    region: "Texas",
    initial_capital: 12000.0,
    risk_tolerance: 0.5,
    persona:
      "A large coastal refinery that buys crude_oil and converts it into refined_fuel and diesel. First buys crude_oil via buy_good(), then calls refine() to convert it, then lists the output via list_good(). Monitors the crack spread (refined price minus crude price). Reduces throughput when crude is expensive relative to refined products; maximises throughput when the spread is wide. Prefers steady volume over speculation.",
    inputs: ["crude_oil"],
    produces: ["refined_fuel", "diesel"],
  },
  {
    name: "EuroRefinery",
    category: "downstream",
    agent_type: "refiner",
    sector: "energy_downstream",
    region: "Europe",
    initial_capital: 10000.0,
    risk_tolerance: 0.45,
    persona:
      "A European refinery with moderate capacity. Sources crude_oil from global markets and sells refined_fuel locally. First buys crude_oil via buy_good(), then calls refine() to convert it, then lists output via list_good(). Subject to cross-region transport costs when buying from non-European producers. Will borrow short-term to stockpile cheap crude ahead of anticipated supply disruptions. Very sensitive to geopolitical events that affect Middle East supply routes.",
    inputs: ["crude_oil"],
    produces: ["refined_fuel"],
  },
  {
    name: "OilTrader",
    category: "financial",
    agent_type: "speculator",
    sector: "commodity_trading",
    region: "NewYork",
    initial_capital: 20000.0,
    risk_tolerance: 0.9,
    persona:
      "An aggressive commodity trading desk that speculates on crude_oil and refined_fuel. Buys when prices are depressed and lists the same goods for resale when prices spike. Interprets geopolitical events and supply shocks as directional trading signals — a supply cut is a buy signal; an SPR release is a sell signal. Comfortable using borrowed capital to amplify positions. Exits positions quickly if the market reverses.",
    produces: [],
  },
  {
    name: "HedgeFund",
    category: "financial",
    agent_type: "speculator",
    sector: "commodity_trading",
    region: "NewYork",
    initial_capital: 30000.0,
    risk_tolerance: 0.75,
    persona:
      "A systematic commodity hedge fund. Uses price history data to identify mean-reversion and momentum opportunities in crude_oil and refined_fuel markets. More disciplined than a pure trader — sets target entry and exit prices based on recent average prices and only acts when there is a clear edge. Manages position size carefully and rarely over-leverages.",
    produces: [],
  },
  {
    name: "EnergyBank",
    category: "financial",
    agent_type: "bank",
    sector: "finance",
    region: "NewYork",
    initial_capital: 50000.0,
    risk_tolerance: 0.35,
    persona:
      "A conservative energy-sector bank with a large capital base. Lends to upstream producers to finance drilling campaigns and to refineries for capital expenditure. Monitors crude price history and agent balances to assess credit risk. Tightens lending standards when multiple agents show distress or when prices are in a sustained decline. Prefers lending to agents with visible inventory and positive recent cash flow.",
    produces: [],
  },
  {
    name: "AirlineConsumer",
    category: "consumer",
    agent_type: "consumer",
    sector: "transportation",
    region: "Europe",
    initial_capital: 25000.0,
    risk_tolerance: 0.4,
    persona:
      "A major international airline with enormous and inelastic demand for refined_fuel and diesel. Fuel is the single largest cost item — every price spike directly hits profitability. Will buy large quantities when prices are low to build a strategic reserve. Will reduce purchase volume (defer non-essential flights) when prices surge. Willing to borrow to stockpile ahead of an anticipated supply disruption.",
    consumption_needs: [
      {
        good_name: "refined_fuel",
        quantity_per_step: 45,
        revenue_per_unit: 90.0,
        reference_price: 45.0,
        price_pass_through: 0.55,
        shortage_penalty_per_unit: 120.0,
        reserve_target_steps: 2,
      },
    ],
    produces: [],
  },
  {
    name: "ChemicalPlant",
    category: "consumer",
    agent_type: "consumer",
    sector: "manufacturing",
    region: "Texas",
    initial_capital: 18000.0,
    risk_tolerance: 0.5,
    persona:
      "A large petrochemical manufacturer that uses crude_oil as a primary feedstock for plastics and chemicals. Buys crude in bulk when it is cheaply available. Moderately price-sensitive — can absorb moderate price increases by passing costs on to industrial buyers, but will reduce input purchasing if crude prices exceed budget thresholds. Monitors upstream supply closely and will borrow to secure a large order at a good price.",
    consumption_needs: [
      {
        good_name: "crude_oil",
        quantity_per_step: 45,
        revenue_per_unit: 75.0,
        reference_price: 35.0,
        price_pass_through: 0.65,
        shortage_penalty_per_unit: 95.0,
        reserve_target_steps: 2,
      },
    ],
    produces: [],
  },
  {
    name: "RetailFuelChain",
    category: "consumer",
    agent_type: "consumer",
    sector: "retail",
    region: "Europe",
    initial_capital: 6000.0,
    risk_tolerance: 0.3,
    persona:
      "A retail fuel distribution network that buys refined_fuel to resell at petrol stations. Operates on very thin margins — a small increase in wholesale fuel prices wipes out profit. Buys frequently in small to medium quantities. Highly price-sensitive: will delay purchases when prices spike, hoping for a correction. Rarely borrows and keeps a tight budget.",
    consumption_needs: [
      {
        good_name: "refined_fuel",
        quantity_per_step: 25,
        revenue_per_unit: 68.0,
        reference_price: 45.0,
        price_pass_through: 0.8,
        shortage_penalty_per_unit: 85.0,
        reserve_target_steps: 1,
      },
    ],
    produces: [],
  },
  {
    name: "ShippingFleet",
    category: "consumer",
    agent_type: "consumer",
    sector: "shipping",
    region: "Europe",
    initial_capital: 20000.0,
    risk_tolerance: 0.5,
    persona:
      "A large international shipping company with steady and sizeable demand for refined_fuel to power its cargo vessels. Fuel is the second-largest operating cost after crew. Buys in large bulk quantities when prices are reasonable and will build a multi-step reserve when prices dip. Moderately price-sensitive — can pass some cost increases on to freight customers but will reduce voyage frequency if fuel costs surge. Willing to borrow short-term to secure a large fuel order at a favourable price.",
    consumption_needs: [
      {
        good_name: "refined_fuel",
        quantity_per_step: 40,
        revenue_per_unit: 85.0,
        reference_price: 45.0,
        price_pass_through: 0.7,
        shortage_penalty_per_unit: 110.0,
        reserve_target_steps: 2,
      },
    ],
    produces: [],
  },
  {
    name: "PowerPlant",
    category: "consumer",
    agent_type: "consumer",
    sector: "utilities",
    region: "MiddleEast",
    initial_capital: 30000.0,
    risk_tolerance: 0.35,
    persona:
      "A state-backed gas and oil-fired power plant with near-inelastic demand for crude_oil and refined_fuel as combustion feedstock for electricity generation. Has a large capital base and long-term supply obligations. Buys steadily every step regardless of short-term price swings but will increase purchase volume opportunistically when prices are below the 3-step average. Very conservative — avoids over-borrowing and prefers to maintain a comfortable cash buffer.",
    consumption_needs: [
      {
        good_name: "crude_oil",
        quantity_per_step: 50,
        revenue_per_unit: 70.0,
        reference_price: 35.0,
        price_pass_through: 0.5,
        shortage_penalty_per_unit: 100.0,
        reserve_target_steps: 2,
      },
      {
        good_name: "refined_fuel",
        quantity_per_step: 10,
        revenue_per_unit: 95.0,
        reference_price: 45.0,
        price_pass_through: 0.45,
        shortage_penalty_per_unit: 120.0,
        reserve_target_steps: 1,
      },
    ],
    produces: [],
  },
];

/** Fresh deep copy of the default roster (so edits never mutate the constant). */
export function cloneDefaultAgents(): AgentProfile[] {
  return DEFAULT_AGENTS.map((a) => structuredClone(a));
}
