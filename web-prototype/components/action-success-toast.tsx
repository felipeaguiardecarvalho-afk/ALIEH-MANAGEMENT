"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";

/** Banner fixo discreto; auto-oculta após `durationMs` (feedback pós-acção, paridade Streamlit). */
export function ActionSuccessToast({
  message,
  visible,
  onDismiss,
  durationMs = 4000,
  className,
}: {
  message: string;
  visible: boolean;
  onDismiss: () => void;
  durationMs?: number;
  className?: string;
}) {
  useEffect(() => {
    if (!visible || !message) return;
    const t = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(t);
  }, [visible, message, durationMs, onDismiss]);

  if (!visible || !message.trim()) return null;

  return (
    <div
      role="status"
      className={cn(
        "pointer-events-none fixed bottom-6 left-1/2 z-[60] max-w-md -translate-x-1/2 rounded-xl border border-[#c7a35b]/45 bg-[#c7a35b]/12 px-4 py-3 text-center text-sm text-foreground shadow-lg backdrop-blur-sm",
        className
      )}
    >
      {message}
    </div>
  );
}
