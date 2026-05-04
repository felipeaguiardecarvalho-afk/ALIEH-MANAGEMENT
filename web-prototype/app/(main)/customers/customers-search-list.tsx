"use client";

import Link from "next/link";
import { useActionState, useMemo, useState } from "react";
import { ArrowUpRight, Pencil, Search, Trash2, Users, X } from "lucide-react";
import { ConfirmDeleteForm } from "@/components/confirm-delete-form";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { deleteCustomerForm, type CustomerFormState } from "@/lib/actions/customers";
import type { CustomerApiRow } from "@/lib/customers-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const initialDeleteState: CustomerFormState = { ok: false, message: "" };

function digits(s: string | null | undefined) {
  return (s ?? "").replace(/\D/g, "");
}

function formatCpfDisplay(cpf: string | null | undefined) {
  const raw = digits(cpf);
  if (!raw) return "—";
  if (raw.length === 11) {
    return `${raw.slice(0, 3)}.${raw.slice(3, 6)}.${raw.slice(6, 9)}-${raw.slice(9)}`;
  }
  return (cpf ?? "").trim();
}

function initials(name: string) {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "—";
}

function customerMatches(c: CustomerApiRow, q: string) {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const needleDigits = digits(needle);
  const haystacks = [
    c.name?.toLowerCase() ?? "",
    c.email?.toLowerCase() ?? "",
    c.instagram?.toLowerCase() ?? "",
    c.customer_code?.toLowerCase() ?? "",
    c.city?.toLowerCase() ?? "",
  ];
  if (haystacks.some((h) => h.includes(needle))) return true;
  if (needleDigits.length > 0) {
    if (digits(c.cpf).includes(needleDigits)) return true;
    if (digits(c.phone).includes(needleDigits)) return true;
  }
  return false;
}

type SortKey = "name" | "code" | "updated";

function sortCustomers(rows: CustomerApiRow[], key: SortKey) {
  const arr = [...rows];
  if (key === "name") {
    arr.sort((a, b) => (a.name || "").localeCompare(b.name || "", "pt"));
  } else if (key === "code") {
    arr.sort((a, b) => (a.customer_code || "").localeCompare(b.customer_code || ""));
  } else {
    arr.sort((a, b) => {
      const da = a.updated_at ?? a.created_at ?? "";
      const db = b.updated_at ?? b.created_at ?? "";
      return db.localeCompare(da);
    });
  }
  return arr;
}

export function CustomersSearchList({
  customers,
  isAdmin,
}: {
  customers: CustomerApiRow[];
  isAdmin: boolean;
}) {
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [selectedId, setSelectedId] = useState<number | null>(
    customers.length > 0 ? customers[0].id : null
  );

  const sorted = useMemo(() => sortCustomers(customers, sortKey), [customers, sortKey]);
  const filtered = useMemo(() => sorted.filter((c) => customerMatches(c, q)), [sorted, q]);
  const selected = useMemo(
    () => filtered.find((c) => c.id === selectedId) ?? customers.find((c) => c.id === selectedId) ?? null,
    [filtered, customers, selectedId]
  );

  return (
    <div className="space-y-4">
      {/* Sticky search strip */}
      <div className="sticky top-0 z-20 -mx-1 flex flex-wrap items-center gap-2 rounded-2xl border border-border/60 bg-background/85 px-3 py-2.5 backdrop-blur supports-[backdrop-filter]:bg-background/65">
        <div className="relative min-w-[260px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por nome, CPF, telefone, email, código…"
            className="h-10 border-transparent bg-muted/30 pl-9 pr-9 text-sm shadow-none focus-visible:bg-background focus-visible:ring-1 focus-visible:ring-[#c7a35b]/40"
            autoComplete="off"
            spellCheck={false}
          />
          {q ? (
            <button
              type="button"
              aria-label="Limpar busca"
              onClick={() => setQ("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
        <Select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="h-10 w-auto min-w-[160px] border-border/60 bg-background text-xs"
          aria-label="Ordenar por"
        >
          <option value="name">Nome (A–Z)</option>
          <option value="code">Código</option>
          <option value="updated">Atualização ↓</option>
        </Select>
        <p className="ml-auto text-xs tabular-nums text-muted-foreground">
          <span className="text-foreground">{filtered.length}</span> de {customers.length}
        </p>
      </div>

      {/* Cockpit grid */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        {/* List */}
        <main className="min-w-0">
          {filtered.length === 0 ? (
            <SearchEmpty q={q} onClear={() => setQ("")} />
          ) : (
            <ul className="overflow-hidden rounded-2xl border border-border/60 bg-background">
              {filtered.map((c) => (
                <CustomerListItem
                  key={c.id}
                  c={c}
                  selected={c.id === selectedId}
                  onSelect={() => setSelectedId(c.id)}
                />
              ))}
            </ul>
          )}
        </main>

        {/* Detail aside */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          {selected ? (
            <CustomerDetailAside customer={selected} isAdmin={isAdmin} />
          ) : (
            <DetailEmpty />
          )}
        </aside>
      </div>
    </div>
  );
}

function CustomerListItem({
  c,
  selected,
  onSelect,
}: {
  c: CustomerApiRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const meta = [formatCpfDisplay(c.cpf), c.phone?.trim(), c.city?.trim()].filter(
    (v) => v && v !== "—"
  );
  return (
    <li
      className={cn(
        "group relative cursor-pointer border-b border-border/30 transition-colors last:border-b-0",
        selected ? "bg-[#c7a35b]/[0.06]" : "hover:bg-muted/[0.04]"
      )}
      onClick={onSelect}
    >
      <div
        className={cn(
          "absolute left-0 top-0 h-full w-0.5 transition-colors",
          selected ? "bg-[#c7a35b]" : "bg-transparent"
        )}
        aria-hidden
      />
      <div className="flex items-center gap-4 px-5 py-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#c7a35b]/30 bg-[#c7a35b]/[0.08] font-mono text-xs font-semibold tracking-wider text-[#d4b36c]">
          {initials(c.name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <p className="truncate font-serif text-base font-medium tracking-tight text-foreground">
              {c.name}
            </p>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#d4b36c]">
              {c.customer_code || "—"}
            </span>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {meta.length ? meta.join(" · ") : "—"}
          </p>
        </div>
        <div className="hidden text-right md:block">
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Atualizado</p>
          <p className="text-[11px] tabular-nums text-muted-foreground">
            {c.updated_at ? formatDate(c.updated_at) : c.created_at ? formatDate(c.created_at) : "—"}
          </p>
        </div>
        <ArrowUpRight
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-opacity",
            selected ? "opacity-100" : "opacity-0 group-hover:opacity-60"
          )}
        />
      </div>
    </li>
  );
}

function CustomerDetailAside({
  customer,
  isAdmin,
}: {
  customer: CustomerApiRow;
  isAdmin: boolean;
}) {
  const [deleteState, deleteAction] = useActionState(deleteCustomerForm, initialDeleteState);

  const addressLine1 = [customer.street?.trim(), customer.number?.trim()].filter(Boolean).join(", ");
  const addressLine2 = [
    customer.neighborhood?.trim(),
    customer.city?.trim(),
    customer.state?.trim(),
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      {/* Hero */}
      <header className="border-b border-border/40 px-6 py-5">
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-[#c7a35b]/40 bg-[#c7a35b]/[0.08] font-mono text-base font-semibold text-[#d4b36c]">
            {initials(customer.name)}
          </div>
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">
              {customer.customer_code || "sem código"}
            </p>
            <h2 className="mt-1 truncate font-serif text-2xl font-semibold tracking-tight text-foreground">
              {customer.name}
            </h2>
            <p className="mt-1 text-[11px] text-muted-foreground">
              criado{" "}
              <span className="text-foreground tabular-nums">
                {customer.created_at ? formatDate(customer.created_at) : "—"}
              </span>
              {customer.updated_at ? (
                <>
                  <span className="mx-2 inline-block h-px w-3 bg-border align-middle" />
                  atualizado{" "}
                  <span className="text-foreground tabular-nums">{formatDate(customer.updated_at)}</span>
                </>
              ) : null}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild variant="luxury" size="sm" className="h-9 gap-1.5">
            <Link href={`/customers/${customer.id}/edit`} prefetch>
              <Pencil className="h-3.5 w-3.5" />
              Editar
            </Link>
          </Button>
          {isAdmin ? (
            <ConfirmDeleteForm
              confirmMessage={`Eliminar definitivamente o cliente «${customer.name}» (${customer.customer_code})?`}
              action={deleteAction}
              className="inline-flex"
            >
              <input type="hidden" name="customer_id" value={String(customer.id)} />
              <SubmitButton
                type="submit"
                variant="outline"
                size="sm"
                className="h-9 gap-1.5 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Eliminar
              </SubmitButton>
            </ConfirmDeleteForm>
          ) : null}
        </div>
        {deleteState.message ? (
          <div className="mt-3">
            <FormAlert state={deleteState} />
          </div>
        ) : null}
      </header>

      {/* Identification */}
      <section className="border-b border-border/40 px-6 py-5">
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Identificação</p>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          <Row label="CPF" value={formatCpfDisplay(customer.cpf)} mono />
          <Row label="RG" value={customer.rg?.trim() || "—"} mono />
          <Row label="Telefone" value={customer.phone?.trim() || "—"} mono />
          <Row label="Email" value={customer.email?.trim() || "—"} />
          <Row label="Instagram" value={customer.instagram?.trim() || "—"} />
        </dl>
      </section>

      {/* Address */}
      <section className="px-6 py-5">
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Endereço</p>
        {!customer.zip_code && !addressLine1 && !addressLine2 ? (
          <p className="text-xs text-muted-foreground">Sem endereço registado.</p>
        ) : (
          <div className="space-y-2 text-sm">
            {customer.zip_code ? (
              <p className="font-mono text-xs text-muted-foreground">
                CEP <span className="text-foreground">{customer.zip_code}</span>
              </p>
            ) : null}
            {addressLine1 ? <p className="text-foreground">{addressLine1}</p> : null}
            {addressLine2 ? <p className="text-muted-foreground">{addressLine2}</p> : null}
            {customer.country ? (
              <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                {customer.country}
              </p>
            ) : null}
          </div>
        )}
      </section>
    </section>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</dt>
      <dd className={cn("mt-0.5 truncate text-sm text-foreground", mono && "font-mono text-xs")}>{value}</dd>
    </div>
  );
}

function DetailEmpty() {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/[0.04] px-6 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border/60 bg-background">
        <Users className="h-5 w-5 text-muted-foreground" strokeWidth={1.4} />
      </div>
      <p className="mt-4 font-serif text-base text-foreground">Selecione um cliente</p>
      <p className="mt-1 max-w-xs text-xs text-muted-foreground">
        Clique numa linha à esquerda para ver os detalhes aqui sem sair desta tela.
      </p>
    </div>
  );
}

function SearchEmpty({ q, onClear }: { q: string; onClear: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/[0.04] px-6 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-border/60 bg-background">
        <Search className="h-5 w-5 text-muted-foreground" strokeWidth={1.4} />
      </div>
      <p className="mt-4 font-serif text-lg tracking-tight text-foreground">Nenhum cliente encontrado</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">
        {q ? (
          <>
            Sem correspondência para “<span className="text-foreground">{q}</span>”. Tente outro termo ou limpe a busca.
          </>
        ) : (
          "Ainda não há clientes."
        )}
      </p>
      {q ? (
        <Button type="button" variant="ghost" size="sm" className="mt-4" onClick={onClear}>
          Limpar busca
        </Button>
      ) : (
        <Button asChild variant="luxury" size="sm" className="mt-4">
          <Link href="/customers/new">Cadastrar primeiro cliente</Link>
        </Button>
      )}
    </div>
  );
}
