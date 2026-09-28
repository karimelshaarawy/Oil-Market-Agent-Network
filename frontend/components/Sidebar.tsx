"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Bot, FileBarChart2, Flame, Waypoints } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV = [
  {
    href: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    activeClass: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/25",
    iconColor: "text-amber-500/70",
    activeIconColor: "text-amber-600 dark:text-amber-400"
  },
  {
    href: "/agents",
    label: "Agents",
    icon: Bot,
    activeClass: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-500/10 dark:text-teal-400 dark:border-teal-500/25",
    iconColor: "text-teal-500/70",
    activeIconColor: "text-teal-600 dark:text-teal-400"
  },
  {
    href: "/map",
    label: "Map",
    icon: Waypoints,
    activeClass: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/25",
    iconColor: "text-rose-500/70",
    activeIconColor: "text-rose-600 dark:text-rose-400"
  },
  {
    href: "/report",
    label: "Report",
    icon: FileBarChart2,
    activeClass: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-400 dark:border-indigo-500/25",
    iconColor: "text-indigo-500/70",
    activeIconColor: "text-indigo-600 dark:text-indigo-400"
  },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 border-r border-border bg-sidebar flex flex-col h-screen sticky top-0 select-none">
      <div className="p-4 border-b border-border flex items-center gap-2.5">
        <div className="p-1.5 rounded-md bg-amber-500/10 border border-amber-500/20 shadow-[0_0_12px_rgba(245,158,11,0.2)]">
          <Flame className="h-4.5 w-4.5 text-primary animate-pulse" />
        </div>
        <span className="font-semibold text-sm tracking-tight text-foreground bg-gradient-to-r from-foreground via-foreground to-foreground/80 bg-clip-text">
          Oil Market Sim
        </span>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {NAV.map(({ href, label, icon: Icon, activeClass, iconColor, activeIconColor }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all duration-250 border",
                active
                  ? activeClass
                  : "text-sidebar-foreground/80 border-transparent hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon 
                className={cn(
                  "h-4 w-4 shrink-0 transition-transform duration-200 group-hover:scale-110", 
                  active ? activeIconColor : cn("text-muted-foreground/70", "group-hover:" + iconColor)
                )} 
              />
              <span className="transition-transform duration-200 group-hover:translate-x-0.5">{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="p-2 border-t border-border">
        <ThemeToggle />
      </div>
    </aside>
  );
}

