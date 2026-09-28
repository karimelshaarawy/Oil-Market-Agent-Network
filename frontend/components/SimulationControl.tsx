"use client";
import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useSimStore } from "@/lib/store";
import { useSimulation } from "@/lib/useSimulation";
import type { SimParams } from "@/types/simulation";
import { AgentBuilderDialog, validateRoster } from "@/components/AgentBuilderDialog";
import {
  Play, Square, Loader2, SlidersHorizontal, Layers, Workflow,
  RefreshCw, Droplet, Factory, TrendingUp, Users, Brain,
  Sparkles, CheckCircle2, AlertCircle, AlignLeft, Newspaper, CalendarDays
} from "lucide-react";
import { cn } from "@/lib/utils";


const SECTORS_CONFIG: Record<
  string, 
  { label: string; icon: React.ComponentType<{ className?: string }>; iconClass: string }
> = {
  include_upstream: { label: "Upstream Extraction", icon: Droplet, iconClass: "text-sky-700 bg-sky-50 border-sky-200 dark:text-sky-400 dark:bg-sky-500/10 dark:border-sky-500/20" },
  include_downstream: { label: "Downstream Refining", icon: Factory, iconClass: "text-purple-700 bg-purple-50 border-purple-200 dark:text-purple-400 dark:bg-purple-500/10 dark:border-purple-500/20" },
  include_financial: { label: "Financial Market", icon: TrendingUp, iconClass: "text-amber-700 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-500/10 dark:border-amber-500/20" },
  include_consumer: { label: "Consumer Demand", icon: Users, iconClass: "text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-500/10 dark:border-emerald-500/20" },
  rag_enabled: { label: "RAG Long-Term Memory", icon: Brain, iconClass: "text-pink-700 bg-pink-50 border-pink-200 dark:text-pink-400 dark:bg-pink-500/10 dark:border-pink-500/20" },
};

export function SimulationControl() {
  const params = useSimStore((s) => s.params);
  const setSimParams = useSimStore((s) => s.setSimParams);
  const { start, stop } = useSimulation();
  const status = useSimStore((s) => s.status);
  const currentStep = useSimStore((s) => s.currentStep);
  const totalSteps = useSimStore((s) => s.totalSteps);
  const currentEvent = useSimStore((s) => s.currentEvent);

  const isRunning = status === "running";
  const progress = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;

  const toggle = (key: keyof SimParams) =>
    setSimParams((p: SimParams) => ({ ...p, [key]: !p[key] }));
  // Toggle ``key`` but, when turning it on, force ``other`` off — the two event
  // sources are mutually exclusive (live news overrides AI events anyway).
  const toggleExclusive = (key: keyof SimParams, other: keyof SimParams) =>
    setSimParams((p: SimParams) => {
      const next = !p[key];
      return { ...p, [key]: next, ...(next ? { [other]: false } : {}) };
    });
  const setNum = (key: keyof SimParams, val: number) =>
    setSimParams((p: SimParams) => ({ ...p, [key]: val }));

  const [agentsOpen, setAgentsOpen] = React.useState(false);
  const setAgents = (updater: (a: SimParams["custom_agents"]) => SimParams["custom_agents"]) =>
    setSimParams((p: SimParams) => ({ ...p, custom_agents: updater(p.custom_agents) }));
  const rosterError = validateRoster(params.custom_agents);

  return (
    <Card className="shadow-lg border-border/80">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-amber-500" />
            Simulation Control
          </CardTitle>
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {/* step progress */}
        {(isRunning || status === "finished") && (
          <div className="space-y-1.5 p-3 rounded-lg bg-secondary/30 border border-border/50">
            <div className="flex justify-between text-xs font-medium">
              <span className="text-muted-foreground flex items-center gap-1.5">
                <Loader2 className={cn("h-3 w-3 text-primary", isRunning && "animate-spin")} />
                Step {currentStep} of {totalSteps}
              </span>
              <span className="text-primary font-mono">{progress}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden relative shadow-inner">
              <div
                className="h-full bg-gradient-to-r from-primary/80 to-primary transition-all duration-500 rounded-full"
                style={{ width: `${progress}%` }}
              />
            </div>
            {currentEvent && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400 leading-normal flex items-start gap-1 pt-1 border-t border-border/20 mt-1 truncate" title={currentEvent}>
                <span className="animate-pulse">⚡</span>
                <span className="truncate">{currentEvent}</span>
              </p>
            )}
          </div>
        )}

        {/* params */}
        <div className="grid grid-cols-3 gap-2.5">
          <NumInput 
            label="Steps" 
            value={params.n_steps} 
            min={1} 
            max={50} 
            onChange={(v) => setNum("n_steps", v)} 
            icon={Layers}
            iconColor="text-sky-600 dark:text-sky-400"
          />
          <NumInput 
            label="Concurrency" 
            value={params.semaphore} 
            min={1} 
            max={10} 
            onChange={(v) => setNum("semaphore", v)} 
            icon={Workflow}
            iconColor="text-teal-600 dark:text-teal-400"
          />
          <NumInput 
            label="Max Iter" 
            value={params.max_iteration} 
            min={1} 
            max={10} 
            onChange={(v) => setNum("max_iteration", v)} 
            icon={RefreshCw}
            iconColor="text-indigo-600 dark:text-indigo-400"
          />
        </div>

        {/* Agent roster builder */}
        <div className="space-y-2 border-t border-border/40 pt-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
            Agents
          </span>
          <button
            type="button"
            onClick={() => setAgentsOpen(true)}
            className="w-full flex items-center justify-between p-2 rounded-md border border-border/70 bg-secondary/30 text-sm hover:bg-secondary/50 transition-colors"
          >
            <span className="flex items-center gap-2.5">
              <span className="p-1 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20">
                <Users className="h-3.5 w-3.5" />
              </span>
              <span className="font-medium text-xs">Configure Agents</span>
            </span>
            <span className="text-xs font-mono text-muted-foreground">
              {params.custom_agents.length}
            </span>
          </button>
          {rosterError && (
            <p className="text-[11px] text-destructive leading-snug flex items-start gap-1.5">
              <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
              {rosterError}
            </p>
          )}
        </div>

        <div className="space-y-2 border-t border-border/40 pt-3">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
            Engine Features
          </span>
          {(
            [
              "rag_enabled",
            ] as (keyof SimParams)[]
          ).map((key) => {
            const config = SECTORS_CONFIG[key];
            if (!config) return null;
            const Icon = config.icon;
            const isChecked = params[key] as boolean;
            return (
              <label 
                key={key} 
                className={cn(
                  "flex items-center justify-between p-2 rounded-md border text-sm cursor-pointer select-none transition-all duration-200",
                  isChecked 
                    ? "bg-secondary/40 border-border/70 shadow-sm" 
                    : "bg-transparent border-transparent text-muted-foreground hover:bg-secondary/20 hover:text-foreground"
                )}
              >
                <div className="flex items-center gap-2.5">
                  <div className={cn("p-1 rounded border shadow-sm transition-transform duration-250", isChecked ? config.iconClass + " scale-105" : "text-muted-foreground/50 bg-muted/20 border-transparent")}>
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <span className="font-medium text-xs">{config.label}</span>
                </div>
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggle(key)}
                  className="accent-primary h-3.5 w-3.5 cursor-pointer rounded"
                />
              </label>
            );
          })}

          {/* Generated events toggle + article input */}
          <div className="border-t border-border/40 pt-3">
            <label 
              className={cn(
                "flex items-center justify-between p-2 rounded-md border text-sm cursor-pointer select-none transition-all duration-200",
                params.use_generated_events 
                  ? "bg-secondary/40 border-border/70 shadow-sm" 
                  : "bg-transparent border-transparent text-muted-foreground hover:bg-secondary/20 hover:text-foreground"
              )}
            >
              <div className="flex items-center gap-2.5">
                <div className={cn("p-1 rounded border shadow-sm transition-transform duration-250", params.use_generated_events ? "text-amber-700 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-500/10 dark:border-amber-500/20 scale-105" : "text-muted-foreground/50 bg-muted/20 border-transparent")}>
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <span className="font-medium text-xs">Inject News Scenario (AI Events)</span>
              </div>
              <input
                type="checkbox"
                checked={params.use_generated_events}
                onChange={() => toggleExclusive("use_generated_events", "use_live_news")}
                className="accent-primary h-3.5 w-3.5 cursor-pointer rounded"
              />
            </label>

            {params.use_generated_events && (
              <div className="mt-2 pl-1 space-y-1.5 animate-fadeIn duration-200">
                <p className="text-[11px] text-muted-foreground leading-normal flex items-start gap-1.5">
                  <AlignLeft className="h-3 w-3 mt-0.5 shrink-0 text-muted-foreground/70" />
                  <span>Paste a news article or market report below. The simulation will dynamically generate scenario events from this context.</span>
                </p>
                <textarea
                  value={params.seed_context_text ?? ""}
                  onChange={(e) => setSimParams((p: SimParams) => ({ ...p, seed_context_text: e.target.value }))}
                  placeholder="e.g. OPEC announced a production cut of 1.5 million barrels per day…"
                  rows={4}
                  className="w-full bg-input border border-border rounded px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 resize-y focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 focus:outline-none font-mono leading-relaxed"
                />
                <p className="text-[10px] text-muted-foreground/70 text-right">
                  {(params.seed_context_text ?? "").length} characters
                </p>
              </div>
            )}
          </div>

          {/* Live oil-news toggle */}
          <div className="border-t border-border/40 pt-3">
            <label
              className={cn(
                "flex items-center justify-between p-2 rounded-md border text-sm cursor-pointer select-none transition-all duration-200",
                params.use_live_news
                  ? "bg-secondary/40 border-border/70 shadow-sm"
                  : "bg-transparent border-transparent text-muted-foreground hover:bg-secondary/20 hover:text-foreground"
              )}
            >
              <div className="flex items-center gap-2.5">
                <div className={cn("p-1 rounded border shadow-sm transition-transform duration-250", params.use_live_news ? "text-cyan-700 bg-cyan-50 border-cyan-200 dark:text-cyan-400 dark:bg-cyan-500/10 dark:border-cyan-500/20 scale-105" : "text-muted-foreground/50 bg-muted/20 border-transparent")}>
                  <Newspaper className="h-3.5 w-3.5" />
                </div>
                <span className="font-medium text-xs">Use Live Oil News (RSS)</span>
              </div>
              <input
                type="checkbox"
                checked={params.use_live_news}
                onChange={() => toggleExclusive("use_live_news", "use_generated_events")}
                className="accent-primary h-3.5 w-3.5 cursor-pointer rounded"
              />
            </label>
            {params.use_live_news && (
              <div className="mt-2 space-y-2.5 animate-fadeIn duration-200">
                <p className="pl-1 text-[11px] text-muted-foreground leading-normal flex items-start gap-1.5">
                  <AlignLeft className="h-3 w-3 mt-0.5 shrink-0 text-muted-foreground/70" />
                  <span>Fetches recent oil headlines, scores them for price impact, and lays the most significant ones across the steps. Overrides scheduled events; falls back to defaults if feeds are unavailable.</span>
                </p>
                <NumInput
                  label="News Lookback (days)"
                  value={params.news_lookback_days}
                  min={1}
                  max={30}
                  onChange={(v) => setNum("news_lookback_days", v)}
                  icon={CalendarDays}
                  iconColor="text-cyan-600 dark:text-cyan-400"
                />
              </div>
            )}
          </div>
        </div>

        <button
          onClick={isRunning ? stop : () => start(params)}
          disabled={!isRunning && rosterError !== null}
          title={!isRunning && rosterError ? rosterError : undefined}
          className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-semibold transition-all duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 ${
            isRunning
              ? "bg-destructive/20 text-destructive border border-destructive/30 hover:bg-destructive/30"
              : "bg-primary text-primary-foreground hover:bg-primary/95 border border-primary/20 hover:scale-[1.01]"
          }`}
        >
          {isRunning ? (
            <><Square className="h-4 w-4 fill-current" /> Stop Simulation</>
          ) : (
            <><Play className="h-4 w-4 fill-current" /> Run Simulation</>
          )}
        </button>

        <AgentBuilderDialog
          open={agentsOpen}
          onClose={() => setAgentsOpen(false)}
          agents={params.custom_agents}
          setAgents={setAgents}
        />
      </CardContent>
    </Card>
  );
}

function NumInput({ 
  label, 
  value, 
  min, 
  max, 
  onChange,
  icon: Icon,
  iconColor,
}: { 
  label: string; 
  value: number; 
  min: number; 
  max: number; 
  onChange: (v: number) => void;
  icon: React.ComponentType<{ className?: string }>;
  iconColor?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-muted-foreground select-none">
      <span className="flex items-center gap-1 font-medium">
        <Icon className={cn("h-3.5 w-3.5", iconColor || "text-muted-foreground/60")} />
        {label}
      </span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="bg-input border border-border rounded px-2.5 py-1 text-foreground text-sm w-full font-mono transition-colors focus:border-primary/45 focus:ring-1 focus:ring-primary/20 focus:outline-none"
      />
    </label>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "running")
    return (
      <Badge variant="secondary" className="gap-1.5 bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-500/10 dark:text-sky-400 dark:border-sky-500/20 px-2 py-0.5 select-none font-medium">
        <Loader2 className="h-3 w-3 animate-spin" />
        Running
      </Badge>
    );
  if (status === "finished")
    return (
      <Badge className="gap-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20 px-2 py-0.5 select-none font-medium">
        <CheckCircle2 className="h-3 w-3" />
        Finished
      </Badge>
    );
  if (status === "error")
    return (
      <Badge variant="destructive" className="gap-1.5 bg-red-50 text-red-700 border border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20 px-2 py-0.5 select-none font-medium">
        <AlertCircle className="h-3 w-3" />
        Error
      </Badge>
    );
  return (
    <Badge variant="outline" className="gap-1.5 bg-muted/25 text-muted-foreground border-border px-2 py-0.5 select-none font-medium">
      <Play className="h-3 w-3 text-muted-foreground/60 fill-current" />
      Idle
    </Badge>
  );
}

