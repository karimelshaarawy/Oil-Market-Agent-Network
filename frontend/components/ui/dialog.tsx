"use client";
import React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  /** Optional node rendered on the right side of the header (e.g. action buttons). */
  headerExtra?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/**
 * Minimal dependency-free modal: portal + fixed overlay, closes on backdrop
 * click or Escape. Styled with the app's design tokens.
 */
export function Dialog({ open, onClose, title, headerExtra, children, className }: DialogProps) {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Prevent background scroll while the modal is open.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fadeIn duration-150"
      onMouseDown={onClose}
    >
      <div
        className={cn(
          "flex flex-col w-full max-w-4xl max-h-[88vh] rounded-xl border border-border bg-background shadow-2xl overflow-hidden",
          className,
        )}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border/60 bg-muted/20">
          <div className="text-sm font-semibold">{title}</div>
          <div className="flex items-center gap-2">
            {headerExtra}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
