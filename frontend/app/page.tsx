import { SimulationControl } from "@/components/SimulationControl";
import { PriceChart } from "@/components/PriceChart";
import { BalanceLeaderboard } from "@/components/BalanceLeaderboard";
import { LiveEventFeed } from "@/components/LiveEventFeed";
import { LayoutDashboard } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-amber-50 border border-amber-200 text-amber-700 dark:bg-amber-500/10 dark:border-amber-500/20 dark:text-amber-400 rounded-lg shadow-sm">
          <LayoutDashboard className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Configure and run the oil market simulation.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1">
          <SimulationControl />
        </div>
        <div className="lg:col-span-2 space-y-4">
          <PriceChart />
          <BalanceLeaderboard />
        </div>
      </div>

      <LiveEventFeed />
    </div>
  );
}
