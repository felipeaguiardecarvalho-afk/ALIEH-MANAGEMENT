"use client";

import { useEffect, useRef, useState } from "react";
import { useFormStatus } from "react-dom";
import { Loader2 } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type State = { ok: boolean; message: string } | undefined;

export function FormAlert({
  state,
  dismissOkAfterMs = 0,
}: {
  state: State;
  /** Se &gt; 0 e `state.ok`, o alerta oculta após N ms (erros permanecem até nova submissão). */
  dismissOkAfterMs?: number;
}) {
  const [dismissed, setDismissed] = useState(false);
  const sigRef = useRef("");

  useEffect(() => {
    const sig = state ? `${state.ok ? 1 : 0}:${state.message}` : "";
    if (sig !== sigRef.current) {
      sigRef.current = sig;
      setDismissed(false);
    }
    if (!state?.message || !state.ok || dismissOkAfterMs <= 0) return;
    const t = window.setTimeout(() => setDismissed(true), dismissOkAfterMs);
    return () => window.clearTimeout(t);
  }, [state, dismissOkAfterMs]);

  if (!state || !state.message || dismissed) return null;
  return (
    <div
      className={cn(
        "rounded-2xl border px-4 py-3 text-sm",
        state.ok
          ? "border-[#c7a35b]/40 bg-[#c7a35b]/10 text-[#d4b36c]"
          : "border-red-500/40 bg-red-500/10 text-red-300"
      )}
    >
      {state.message}
    </div>
  );
}

export function SubmitButton({
  children,
  disabled,
  ...props
}: ButtonProps) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="luxury" {...props} disabled={pending || Boolean(disabled)}>
      {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      {children}
    </Button>
  );
}
