"use client";
import { useSimStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";

const PALETTE = [
  "#f59e0b", // Gold / Amber
  "#38bdf8", // Sky Blue
  "#a78bfa", // Purple
  "#34d399", // Emerald
  "#fb7185", // Rose
  "#2dd4bf", // Teal
  "#fbbf24", // Yellow
];

export function PriceChart() {
  const priceHistory = useSimStore((s) => s.priceHistory);
  const goods = Object.keys(priceHistory);

  // Merge all goods into per-step rows
  const allSteps = Array.from(
    new Set(goods.flatMap((g) => priceHistory[g].map((p) => p.step)))
  ).sort((a, b) => a - b);

  const data = allSteps.map((step) => {
    const row: Record<string, number | string> = { step };
    for (const good of goods) {
      const pt = priceHistory[good].findLast((p) => p.step <= step);
      if (pt) row[good] = pt.price;
    }
    return row;
  });

  return (
    <Card className="shadow-md border-border/80">
      <CardHeader className="pb-3 border-b border-border/40 bg-muted/10">
        <CardTitle className="text-xs font-semibold flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-emerald-500" />
          Good Prices
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        {data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center gap-2 select-none">
            <TrendingUp className="h-8 w-8 text-muted-foreground/30 animate-pulse" />
            <p className="text-xs text-muted-foreground">No price data yet.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="step" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
              <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} width={48} />
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
                cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {goods.map((good, i) => (
                <Line
                  key={good}
                  type="monotone"
                  dataKey={good}
                  stroke={PALETTE[i % PALETTE.length]}
                  dot={false}
                  strokeWidth={2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
