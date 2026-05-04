"use client";

import { useActionState } from "react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { upsertUatRecord, type UatState } from "@/lib/actions/uat";
import { UAT_STATUS_LABELS, UAT_STATUS_ORDER, type UatStatus } from "@/lib/domain";

const initialState: UatState = { ok: false, message: "" };

export function UatCaseCard({
  code,
  title,
  description,
  currentStatus,
  currentNotes,
  lastUpdatedAt,
  lastUser,
}: {
  code: string;
  title: string;
  description: string;
  currentStatus: UatStatus;
  currentNotes: string;
  lastUpdatedAt: string | null;
  lastUser: string | null;
}) {
  const [state, formAction] = useActionState(upsertUatRecord, initialState);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">
          <span className="font-mono text-sm text-[#d4b36c]">{code}</span>
          <span className="ml-3">{title}</span>
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form action={formAction} className="space-y-4">
          <input type="hidden" name="test_id" value={code} />
          <FormAlert state={state.message ? state : undefined} />

          <div className="grid gap-4 md:grid-cols-[1fr_2fr]">
            <div className="space-y-2">
              <Label htmlFor={`status-${code}`}>Resultado</Label>
              <Select id={`status-${code}`} name="status" defaultValue={currentStatus}>
                {UAT_STATUS_ORDER.map((status) => (
                  <option key={status} value={status}>
                    {UAT_STATUS_LABELS[status]}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor={`notes-${code}`}>Notas (opcional)</Label>
              <Textarea id={`notes-${code}`} name="notes" defaultValue={currentNotes} rows={2} />
            </div>
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              {lastUpdatedAt
                ? `Último registro: ${lastUpdatedAt}${lastUser ? ` · ${lastUser}` : ""}`
                : "Sem registro anterior."}
            </p>
            <SubmitButton>Gravar resultado</SubmitButton>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
