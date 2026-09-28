import { Waypoints } from "lucide-react";
import { AgentMapCanvas } from "@/components/map/AgentMapCanvas";

export default function MapPage() {
  return (
    <div className="flex flex-col h-full gap-4">
      <div className="flex items-center gap-3 shrink-0">
        <div className="p-2 bg-rose-50 border border-rose-200 text-rose-700 dark:bg-rose-500/10 dark:border-rose-500/20 dark:text-rose-400 rounded-lg shadow-sm">
          <Waypoints className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Map</h1>
          <p className="text-sm text-muted-foreground">
            Live supply-chain network — watch agents trade, produce, and lend in real time.
          </p>
        </div>
      </div>

      <div className="flex-1 min-h-[480px]">
        <AgentMapCanvas />
      </div>
    </div>
  );
}
