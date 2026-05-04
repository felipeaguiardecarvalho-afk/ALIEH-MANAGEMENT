"use client";

import Link from "next/link";
import { useActionState } from "react";
import { login, type LoginFormState } from "@/lib/actions/auth";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

const initial: LoginFormState = { ok: false, message: "" };

type Props = {
  tenantOptions: string[];
  showTenantPicker: boolean;
  openMode: boolean;
};

export function LoginForm({ tenantOptions, showTenantPicker, openMode }: Props) {
  const [state, formAction] = useActionState(login, initial);

  if (openMode) {
    return (
      <div className="space-y-3 text-sm text-muted-foreground">
        <p>
          Modo aberto: <code className="text-xs">ALIEH_PROTOTYPE_OPEN=1</code> — middleware não
          exige sessão.
        </p>
        <Link
          href="/dashboard"
          className="inline-flex rounded-full border border-white/22 px-4 py-2 text-foreground hover:bg-white/10"
        >
          Ir ao painel
        </Link>
      </div>
    );
  }

  return (
    <form action={formAction} className="space-y-5">
      <FormAlert state={state.message ? state : undefined} />

      {showTenantPicker ? (
        <div className="space-y-2">
          <Label htmlFor="tenant_id">Empresa (inquilino)</Label>
          <Select id="tenant_id" name="tenant_id" defaultValue={tenantOptions[0] ?? "default"} required>
            {tenantOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </div>
      ) : tenantOptions.length > 0 ? (
        <input type="hidden" name="tenant_id" value={tenantOptions[0] ?? "default"} />
      ) : null}

      <div className="space-y-2">
        <Label htmlFor="username">Utilizador</Label>
        <Input id="username" name="username" autoComplete="username" required />
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Senha</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </div>

      <SubmitButton className="w-full">Entrar</SubmitButton>
    </form>
  );
}
