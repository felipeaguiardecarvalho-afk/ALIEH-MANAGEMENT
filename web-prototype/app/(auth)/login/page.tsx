import { LoginForm } from "./login-form";
import { countUsers, listTenantIdsWithUsers } from "@/lib/auth/users-db";
import { legacyCredentialsConfigured } from "@/lib/auth/password";
import { isPrototypeOpenEffective } from "@/lib/env/alieh-runtime";

export default async function LoginPage() {
  const openMode = isPrototypeOpenEffective();
  const hasUsers = (await countUsers()) > 0;
  const tenants = hasUsers ? await listTenantIdsWithUsers() : [];
  const tenantOptions = hasUsers ? (tenants.length > 0 ? tenants : ["default"]) : [];
  const showTenantPicker = tenantOptions.length > 1;
  const legacy = legacyCredentialsConfigured();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-16">
      <div className="w-full max-w-md space-y-8 rounded-2xl border border-white/10 bg-black/60 p-8 shadow-2xl backdrop-blur-xl">
        <div>
          <h1 className="font-serif text-2xl tracking-wide">ALIEH — Acesso</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Protótipo Next.js: sessão em cookie httpOnly (JWT), paridade com utilizadores na BD
            (PBKDF2 como em <code className="text-xs">utils/password_hash.py</code>) ou credencial
            legacy <code className="text-xs">ALIEH_AUTH_*</code>.
          </p>
        </div>

        {!hasUsers && !legacy && !openMode ? (
          <p className="text-sm text-amber-200/90">
            Nenhum modo de login disponível. Crie linhas em <code className="text-xs">users</code>{" "}
            (fora deste protótipo) ou defina <code className="text-xs">ALIEH_AUTH_USERNAME</code> /{" "}
            <code className="text-xs">ALIEH_AUTH_PASSWORD</code>, ou{" "}
            <code className="text-xs">ALIEH_PROTOTYPE_OPEN=1</code> para desenvolvimento.
          </p>
        ) : null}

        <LoginForm
          tenantOptions={tenantOptions}
          showTenantPicker={showTenantPicker}
          openMode={openMode}
        />
      </div>
    </div>
  );
}
