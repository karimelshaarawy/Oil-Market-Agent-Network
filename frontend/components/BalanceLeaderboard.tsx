"use client";
import { useState } from "react";
import { useSimStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Trophy, Coins } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Cell,
} from "recharts";

const BAR_PALETTE = [
  "#facc15", // Vivid Yellow
  "#06b6d4", // Vivid Cyan
  "#a855f7", // Vivid Purple
  "#10b981", // Vivid Emerald
  "#ef4444", // Vivid Red
  "#ec4899", // Vivid Pink
  "#14b8a6", // Vivid Teal
  "#f97316", // Vivid Orange
];

export function BalanceLeaderboard() {
  const balances = useSimStore((s) => s.balances);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const data = Object.entries(balances)
    .map(([name, balance]) => ({
      name,
      balance, // Precise balance for sorting and tooltips
      clampedBalance: Math.max(0, balance), // Clamped to zero for visual bar rendering
    }))
    .sort((a, b) => b.balance - a.balance);

  // 36px per bar gives clear labels; minimum 160px
  const chartHeight = Math.max(160, data.length * 36);

  return (
    <Card className="shadow-md border-border/80">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
        <CardTitle className="text-xs font-semibold flex items-center gap-2">
          <Trophy className="h-4 w-4 text-amber-500" />
          Agent Balances
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        {data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center gap-2 select-none">
            <Coins className="h-8 w-8 text-muted-foreground/30 animate-pulse" />
            <p className="text-xs text-muted-foreground">No balance data yet.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 110, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "var(--foreground)" }} width={110} />
              <Tooltip
                contentStyle={{ 
                  background: "var(--card)", 
                  border: "1px solid var(--border)", 
                  borderRadius: "8px", 
                  fontSize: "12px",
                  boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.15)"
                }}
                itemStyle={{ color: "var(--foreground)" }}
                labelStyle={{ color: "var(--muted-foreground)", fontWeight: 600 }}
                cursor={{ fill: "var(--muted)", opacity: 0.15 }}
                formatter={(v, name, props) => {
                  const actualBalance = props.payload?.balance ?? Number(v);
                  const formatted = actualBalance < 0
                    ? `-$${Math.abs(actualBalance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : `$${actualBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                  return [formatted, "Balance"];
                }}
              />
              <Bar dataKey="clampedBalance" radius={[0, 4, 4, 0]}>
                {data.map((_, i) => (
                  <Cell 
                    key={i} 
                    fill={BAR_PALETTE[i % BAR_PALETTE.length]} 
                    opacity={hoveredIndex === null || hoveredIndex === i ? 1 : 0.65}
                    className="transition-all duration-300 cursor-pointer"
                    onMouseEnter={() => setHoveredIndex(i)}
                    onMouseLeave={() => setHoveredIndex(null)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

