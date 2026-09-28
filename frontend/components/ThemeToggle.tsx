"use client";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Avoid hydration mismatch: theme is only known on the client.
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "group flex w-full items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all duration-250 border border-transparent",
        "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground select-none",
      )}
    >
      {/* Render a neutral icon until mounted to keep SSR/CSR markup stable */}
      {!mounted ? (
        <span className="h-4 w-4 shrink-0" />
      ) : isDark ? (
        <Sun className="h-4 w-4 shrink-0 text-muted-foreground/70 transition-transform duration-200 group-hover:scale-110" />
      ) : (
        <Moon className="h-4 w-4 shrink-0 text-muted-foreground/70 transition-transform duration-200 group-hover:scale-110" />
      )}
      <span className="transition-transform duration-200 group-hover:translate-x-0.5">
        {mounted ? (isDark ? "Light mode" : "Dark mode") : "Theme"}
      </span>
    </button>
  );
}
