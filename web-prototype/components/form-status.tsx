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
          ? "border-[#c7a35b]/55 bg-[#c7a35b]/14 text-[#efe5cf]"
          : "border-red-500/55 bg-red-500/14 text-red-200"
      )}
    >
      {state.message}
    </div>
  );
}

export function SubmitButton({
  children,
  disabled,
  blockWhilePending = true,
  ...props
}: ButtonProps & { blockWhilePending?: boolean }) {
  const { pending } = useFormStatus();
  const wait = blockWhilePending && pending;
  return (
    <Button type="submit" variant="luxury" {...props} disabled={wait || Boolean(disabled)}>
      {pending ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden /> : null}
      {children}
    </Button>
  );
}
