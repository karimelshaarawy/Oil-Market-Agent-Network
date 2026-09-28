"use client";
import React from "react";
import { Dialog } from "@/components/ui/dialog";
import { AGENT_TYPE_CONFIG } from "@/components/AgentCard";
import { cn } from "@/lib/utils";
import {
  AGENT_TYPES,
  AGENT_TYPE_LABEL,
  KNOWN_GOODS,
  REGIONS,
  cloneDefaultAgents,
  defaultConsumptionNeed,
  makeDefaultAgent,
} from "@/lib/defaultAgents";
import type {
  AgentProfile,
  AgentTypeName,
  ConsumptionNeed,
} from "@/types/simulation";
import {
  Plus,
  Trash2,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  X as XIcon,
} from "lucide-react";

/**
 * Validate the roster the same way the backend does. Returns an error string to
 * display, or null when the roster is runnable.
 */
export function validateRoster(agents: AgentProfile[]): string | null {
  if (!agents.length) return "Add at least one agent.";
  const seen = new Set<string>();
  for (const a of agents) {
    const name = a.name.trim();
    if (!name) return "Every agent needs a name.";
    if (seen.has(name)) return `Duplicate agent name "${name}".`;
    seen.add(name);
    if (!Number.isFinite(a.initial_capital) || a.initial_capital < 0)
      return `${name}: capital must be ≥ 0.`;
    if (a.risk_tolerance < 0 || a.risk_tolerance > 1)
      return `${name}: risk tolerance must be between 0 and 1.`;
    if (a.agent_type === "consumer" && !(a.consumption_needs?.length))
      return `${name}: a consumer needs at least one consumption need.`;
  }
  return null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  agents: AgentProfile[];
  setAgents: (updater: (a: AgentProfile[]) => AgentProfile[]) => void;
}

export function AgentBuilderDialog({ open, onClose, agents, setAgents }: Props) {
  const [selected, setSelected] = React.useState(0);
  const [addType, setAddType] = React.useState<AgentTypeName>("firm");

  const idx = Math.min(selected, Math.max(0, agents.length - 1));
  const agent = agents[idx];

  const patch = (changes: Partial<AgentProfile>) =>
    setAgents((a) => a.map((x, i) => (i === idx ? { ...x, ...changes } : x)));

  const addAgent = () => {
    const existing = new Set(agents.map((a) => a.name));
    let name = "NewAgent";
    let n = 1;
    while (existing.has(name)) name = `NewAgent${++n}`;
    setAgents((a) => [...a, makeDefaultAgent(addType, { name })]);
    setSelected(agents.length);
  };

  const removeAgent = (i: number) => {
    setAgents((a) => a.filter((_, j) => j !== i));
    setSelected((s) => (i <= s ? Math.max(0, s - 1) : s));
  };

  const resetDefaults = () => {
    setAgents(() => cloneDefaultAgents());
    setSelected(0);
  };

  const changeType = (type: AgentTypeName) =>
    patch(
      makeDefaultAgent(type, {
        name: agent.name,
        region: agent.region,
        initial_capital: agent.initial_capital,
        risk_tolerance: agent.risk_tolerance,
        persona: agent.persona,
      }),
    );

  const error = validateRoster(agents);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Configure Agents (${agents.length})`}
      headerExtra={
        <button
          type="button"
          onClick={resetDefaults}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-muted-foreground border border-border/60 hover:bg-secondary/60 hover:text-foreground transition-colors"
        >
          <RotateCcw className="h-3 w-3" /> Reset to defaults
        </button>
      }
    >
      <div className="flex flex-1 min-h-0">
        {/* ── Roster list ─────────────────────────────────────────────── */}
        <div className="w-56 shrink-0 border-r border-border/60 flex flex-col bg-muted/10">
          <div className="p-2 border-b border-border/50 flex items-center gap-1.5">
            <select
              value={addType}
              onChange={(e) => setAddType(e.target.value as AgentTypeName)}
              className="flex-1 bg-input border border-border rounded px-1.5 py-1 text-xs text-foreground focus:outline-none focus:border-primary/45"
            >
              {AGENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {AGENT_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={addAgent}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-primary/90 text-primary-foreground hover:bg-primary transition-colors"
            >
              <Plus className="h-3 w-3" /> Add
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-1.5 space-y-1">
            {agents.map((a, i) => {
              const conf = AGENT_TYPE_CONFIG[a.agent_type] ?? {};
              const Icon = conf.icon;
              return (
                <div
                  key={i}
                  onClick={() => setSelected(i)}
                  className={cn(
                    "group flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer text-xs transition-colors",
                    i === idx
                      ? "bg-secondary/70 border border-border/70"
                      : "border border-transparent hover:bg-secondary/30",
                  )}
                >
                  {Icon && (
                    <span className={cn("p-1 rounded shrink-0", conf.color)}>
                      <Icon className="h-3 w-3" />
                    </span>
                  )}
                  <span className="flex-1 truncate font-medium">{a.name || "(unnamed)"}</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeAgent(i);
                    }}
                    aria-label={`Remove ${a.name}`}
                    className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
            {!agents.length && (
              <p className="text-[11px] text-muted-foreground text-center py-6">
                No agents. Click “Add”.
              </p>
            )}
          </div>
          {error && (
            <p className="p-2 text-[11px] text-destructive border-t border-border/50 leading-snug">
              {error}
            </p>
          )}
        </div>

        {/* ── Editor ──────────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-y-auto p-4">
          {agent ? (
            <AgentEditor
              agent={agent}
              onPatch={patch}
              onChangeType={changeType}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Select or add an agent to edit.</p>
          )}
        </div>
      </div>
    </Dialog>
  );
}

// ── Editor for a single agent ──────────────────────────────────────────────

function AgentEditor({
  agent,
  onPatch,
  onChangeType,
}: {
  agent: AgentProfile;
  onPatch: (changes: Partial<AgentProfile>) => void;
  onChangeType: (type: AgentTypeName) => void;
}) {
  const [advanced, setAdvanced] = React.useState(false);
  const isFirm = agent.agent_type === "firm";
  const isRefiner = agent.agent_type === "refiner";
  const isConsumer = agent.agent_type === "consumer";

  return (
    <div className="space-y-3.5">
      {/* Quick fields */}
      <div className="grid grid-cols-2 gap-3">
        <TextField
          label="Name"
          value={agent.name}
          onChange={(v) => onPatch({ name: v })}
        />
        <Labeled label="Type">
          <select
            value={agent.agent_type}
            onChange={(e) => onChangeType(e.target.value as AgentTypeName)}
            className={inputCls}
          >
            {AGENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {AGENT_TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </Labeled>
        <TextField
          label="Region"
          value={agent.region}
          onChange={(v) => onPatch({ region: v })}
          list="known-regions"
        />
        <TextField
          label="Sector"
          value={agent.sector}
          onChange={(v) => onPatch({ sector: v })}
        />
        <NumberField
          label="Initial Capital"
          value={agent.initial_capital}
          min={0}
          step={1000}
          onChange={(v) => onPatch({ initial_capital: v })}
        />
        <NumberField
          label="Risk Tolerance (0–1)"
          value={agent.risk_tolerance}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => onPatch({ risk_tolerance: v })}
        />
      </div>

      <datalist id="known-regions">
        {REGIONS.map((r) => (
          <option key={r} value={r} />
        ))}
      </datalist>
      <datalist id="known-goods">
        {KNOWN_GOODS.map((g) => (
          <option key={g} value={g} />
        ))}
      </datalist>

      {/* Advanced */}
      <button
        type="button"
        onClick={() => setAdvanced((v) => !v)}
        className="flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors pt-1"
      >
        {advanced ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        Advanced
      </button>

      {advanced && (
        <div className="space-y-3.5 border-l-2 border-border/40 pl-3 ml-0.5 animate-fadeIn duration-150">
          <Labeled label="Persona">
            <textarea
              value={agent.persona}
              onChange={(e) => onPatch({ persona: e.target.value })}
              rows={4}
              placeholder="Describe this agent's strategy and behaviour…"
              className={cn(inputCls, "font-mono leading-relaxed resize-y")}
            />
          </Labeled>

          {(isFirm || isRefiner) && (
            <GoodsChips
              label="Produces"
              goods={agent.produces}
              onChange={(produces) => onPatch({ produces })}
            />
          )}

          {isRefiner && (
            <GoodsChips
              label="Inputs"
              goods={agent.inputs ?? []}
              onChange={(inputs) => onPatch({ inputs })}
            />
          )}

          {isFirm && (
            <UnitCostsEditor
              produces={agent.produces}
              unitCosts={agent.unit_costs ?? {}}
              onChange={(unit_costs) => onPatch({ unit_costs })}
            />
          )}

          {isConsumer && (
            <ConsumptionNeedsEditor
              needs={agent.consumption_needs ?? []}
              onChange={(consumption_needs) => onPatch({ consumption_needs })}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ── Small field primitives ─────────────────────────────────────────────────

const inputCls =
  "w-full bg-input border border-border rounded px-2.5 py-1 text-sm text-foreground focus:outline-none focus:border-primary/45 focus:ring-1 focus:ring-primary/20 transition-colors";

function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground select-none">
      <span className="font-medium">{label}</span>
      {children}
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  list,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  list?: string;
}) {
  return (
    <Labeled label={label}>
      <input
        type="text"
        value={value}
        list={list}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
    </Labeled>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <Labeled label={label}>
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className={cn(inputCls, "font-mono")}
      />
    </Labeled>
  );
}

// ── Goods selector (produces / inputs) ─────────────────────────────────────
// Restricted to the known oil goods via a fixed dropdown — no free text, so a
// good name can never be mistyped and break matching against other agents.

function GoodsChips({
  label,
  goods,
  onChange,
}: {
  label: string;
  goods: string[];
  onChange: (goods: string[]) => void;
}) {
  const available = KNOWN_GOODS.filter((g) => !goods.includes(g));
  return (
    <Labeled label={label}>
      <div className="flex flex-wrap items-center gap-1.5">
        {goods.map((g) => (
          <span
            key={g}
            className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-secondary/60 border border-border/60"
          >
            {g}
            <button
              type="button"
              onClick={() => onChange(goods.filter((x) => x !== g))}
              aria-label={`Remove ${g}`}
              className="text-muted-foreground hover:text-destructive"
            >
              <XIcon className="h-3 w-3" />
            </button>
          </span>
        ))}
        {available.length > 0 && (
          <select
            value=""
            onChange={(e) => {
              if (e.target.value) onChange([...goods, e.target.value]);
            }}
            className="bg-input border border-border rounded px-2 py-0.5 text-xs focus:outline-none focus:border-primary/45"
          >
            <option value="" disabled>
              add good…
            </option>
            {available.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        )}
      </div>
    </Labeled>
  );
}

// ── Unit costs editor (firm) ────────────────────────────────────────────────

function UnitCostsEditor({
  produces,
  unitCosts,
  onChange,
}: {
  produces: string[];
  unitCosts: Record<string, number>;
  onChange: (costs: Record<string, number>) => void;
}) {
  if (!produces.length) {
    return (
      <p className="text-[11px] text-muted-foreground">
        Add a produced good to set its unit cost.
      </p>
    );
  }
  return (
    <Labeled label="Unit Costs (per produced good)">
      <div className="space-y-1.5">
        {produces.map((g) => (
          <div key={g} className="flex items-center gap-2">
            <span className="text-xs w-28 truncate font-mono">{g}</span>
            <input
              type="number"
              min={0}
              step={1}
              value={Number.isFinite(unitCosts[g]) ? unitCosts[g] : ""}
              onChange={(e) => onChange({ ...unitCosts, [g]: Number(e.target.value) })}
              className={cn(inputCls, "font-mono flex-1")}
            />
          </div>
        ))}
      </div>
    </Labeled>
  );
}

// ── Consumption needs editor (consumer) ─────────────────────────────────────

const NEED_NUM_FIELDS: { key: keyof ConsumptionNeed; label: string; step?: number }[] = [
  { key: "quantity_per_step", label: "Qty/step", step: 1 },
  { key: "revenue_per_unit", label: "Revenue/unit", step: 1 },
  { key: "reference_price", label: "Ref. price", step: 1 },
  { key: "price_pass_through", label: "Pass-through (0–1)", step: 0.05 },
  { key: "shortage_penalty_per_unit", label: "Shortage penalty", step: 1 },
  { key: "reserve_target_steps", label: "Reserve steps", step: 1 },
];

function ConsumptionNeedsEditor({
  needs,
  onChange,
}: {
  needs: ConsumptionNeed[];
  onChange: (needs: ConsumptionNeed[]) => void;
}) {
  const patchNeed = (i: number, changes: Partial<ConsumptionNeed>) =>
    onChange(needs.map((n, j) => (j === i ? { ...n, ...changes } : n)));

  return (
    <Labeled label="Consumption Needs">
      <div className="space-y-2.5">
        {needs.map((need, i) => (
          <div key={i} className="rounded-md border border-border/60 p-2.5 space-y-2 bg-muted/10">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={need.good_name}
                list="known-goods"
                onChange={(e) => patchNeed(i, { good_name: e.target.value })}
                className={cn(inputCls, "font-mono flex-1")}
                placeholder="good_name"
              />
              <button
                type="button"
                onClick={() => onChange(needs.filter((_, j) => j !== i))}
                aria-label="Remove need"
                className="text-muted-foreground hover:text-destructive shrink-0"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {NEED_NUM_FIELDS.map((f) => (
                <label key={f.key} className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                  <span>{f.label}</span>
                  <input
                    type="number"
                    step={f.step}
                    value={Number.isFinite(need[f.key]) ? (need[f.key] as number) : ""}
                    onChange={(e) => patchNeed(i, { [f.key]: Number(e.target.value) })}
                    className={cn(inputCls, "font-mono py-0.5")}
                  />
                </label>
              ))}
            </div>
          </div>
        ))}
        <button
          type="button"
          onClick={() => onChange([...needs, defaultConsumptionNeed()])}
          className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          <Plus className="h-3 w-3" /> Add need
        </button>
      </div>
    </Labeled>
  );
}
