import type { AgentHistory, SimSnapshot } from "@/types/simulation";

const BASE = "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const data = (await res.json()) as T & { error?: string };
  if (data && typeof data === "object" && "error" in data && data.error) {
    throw new Error(String(data.error));
  }
  return data;
}

export const api = {
  listSimulations: () => get<{ simulations: string[] }>("/simulate/list"),
  snapshot: (id: string) => get<SimSnapshot>(`/simulate/${id}/snapshot`),
  listAgents: (id: string) => get<{ agents: { agent_id: number; name: string; agent_type: string; sector: string; balance: number }[] }>(`/simulate/${id}/agents`),
  agentHistory: (id: string, name: string) =>
    get<AgentHistory>(`/simulate/${id}/agent/${encodeURIComponent(name)}/history`),

  async reportChat(simulationId: string, message: string): Promise<string> {
    const res = await fetch(`${BASE}/report/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulation_id: simulationId, message }),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const text = await res.text();
    const line = text.trim().split("\n").pop() ?? "{}";
    const obj = JSON.parse(line);
    if (obj.error) throw new Error(obj.error);
    return obj.content ?? "";
  },

  async agentChat(simulationId: string, agentName: string, message: string): Promise<string> {
    const res = await fetch(`${BASE}/agent/${encodeURIComponent(agentName)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulation_id: simulationId, message }),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const text = await res.text();
    const line = text.trim().split("\n").pop() ?? "{}";
    const obj = JSON.parse(line);
    if (obj.error) throw new Error(obj.error);
    return obj.content ?? "";
  },
};
