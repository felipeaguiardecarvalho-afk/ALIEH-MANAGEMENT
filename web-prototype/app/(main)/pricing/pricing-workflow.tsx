"use client";

import {
  useActionState,
  useCallback,
  useEffect,
  useMemo,
  useOptimistic,
  useRef,
  useState,
} from "react";
import type { SkuCostPickerOption } from "@/lib/costs-types";
import { useFormStatus } from "react-dom";
import { ArrowDown, ArrowDownRight, ArrowUpRight } from "lucide-react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { computeSkuPricingPreview, saveSkuPricing, type PricingState } from "@/lib/actions/pricing";
import type { PriceHistoryApiRow, PricingRecordApiRow, PricingSnapshotApi } from "@/lib/pricing-api";
import { formatCurrency, formatDate } from "@/lib/format";
import {
  invalidatePricingInsightCache,
  loadPricingInsightBundleCached,
} from "@/lib/pricing-insight-client-cache";
import type { SkuMasterRow } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const initialState: PricingState = { ok: false, message: "" };

function mergePricingState(prev: PricingState, patch: Partial<PricingState>): PricingState {
  return { ...prev, ...patch };
}

type OptimisticSkuRowPatch = { sku: string; sellingPrice: number };

function applySkuRowPrice(rows: SkuMasterRow[], patch: OptimisticSkuRowPatch): SkuMasterRow[] {
  return rows.map((r) =>
    r.sku === patch.sku ? { ...r, sellingPrice: patch.sellingPrice } : r
  );
}

type PickMode = "sku" | "name";

function kindLabel(k: number) {
  return k === 1 ? "R$ fixo" : "%";
}

export function PricingWorkflow({
  rows,
  pickByName,
}: {
  rows: SkuMasterRow[];
  pickByName: SkuCostPickerOption[];
}) {
  // ───── Logic preserved verbatim ─────
  const [state, saveAction] = useActionState(saveSkuPricing, initialState);
  const [displayState, addOptimisticState] = useOptimistic(state, mergePricingState);
  const [displayRows, addOptimisticRowPrice] = useOptimistic(rows, applySkuRowPrice);

  const [pickMode, setPickMode] = useState<PickMode>("sku");
  const [selectedSku, setSelectedSku] = useState(rows[0]?.sku ?? "");
  const [markup, setMarkup] = useState(0);
  const [taxes, setTaxes] = useState(0);
  const [interest, setInterest] = useState(0);
  const [markupKind, setMarkupKind] = useState<0 | 1>(0);
  const [taxesKind, setTaxesKind] = useState<0 | 1>(0);
  const [interestKind, setInterestKind] = useState<0 | 1>(0);

  const [snapshot, setSnapshot] = useState<PricingSnapshotApi | null>(null);
  const [records, setRecords] = useState<PricingRecordApiRow[]>([]);
  const [prices, setPrices] = useState<PriceHistoryApiRow[]>([]);
  const [loadingInsight, setLoadingInsight] = useState(true);
  const [preview, setPreview] = useState<{
    priceBefore: number;
    priceWithTaxes: number;
    targetPrice: number;
  } | null>(null);

  const formAction = useCallback(
    (fd: FormData) => {
      const sku = String(fd.get("sku") ?? "").trim();
      const tp = preview?.targetPrice ?? 0;
      if (sku && tp > 0) {
        addOptimisticRowPrice({ sku, sellingPrice: tp });
        addOptimisticState({ ok: false, message: "A activar precificação no servidor…" });
      }
      return saveAction(fd);
    },
    [saveAction, addOptimisticRowPrice, addOptimisticState, preview]
  );

  const insightRequestIdRef = useRef(0);
  const computeRequestIdRef = useRef(0);

  const nameLabelToSku = useMemo(() => {
    const m = new Map<string, string>();
    for (const o of pickByName) m.set(o.label, o.sku);
    return m;
  }, [pickByName]);

  const active = useMemo(
    () => displayRows.find((row) => row.sku === selectedSku),
    [displayRows, selectedSku]
  );

  useEffect(() => {
    if (pickMode === "sku") {
      const skus = rows.map((r) => r.sku);
      if (!selectedSku || !skus.includes(selectedSku)) {
        setSelectedSku(rows[0]?.sku ?? "");
      }
      return;
    }
    if (!pickByName.length) {
      setPickMode("sku");
      return;
    }
    if (!pickByName.some((o) => o.sku === selectedSku)) {
      setSelectedSku(pickByName[0].sku);
    }
  }, [pickMode, pickByName, rows, selectedSku]);

  const avgCost = active?.avgUnitCost ?? 0;
  const currentPrice = active?.sellingPrice ?? 0;
  const stock = active?.totalStock ?? 0;
  const displayPreview = preview ?? {
    priceBefore: 0,
    priceWithTaxes: 0,
    targetPrice: 0,
  };
  const canSave = avgCost > 0 && displayPreview.targetPrice > 0;

  const targetVsCurrentPct =
    currentPrice > 0 && displayPreview.targetPrice > 0
      ? ((displayPreview.targetPrice - currentPrice) / currentPrice) * 100
      : null;

  const scheduleComputePreview = useCallback(async () => {
    const rid = ++computeRequestIdRef.current;
    if (avgCost <= 0 || !selectedSku.trim()) {
      if (rid !== computeRequestIdRef.current) return;
      setPreview({ priceBefore: 0, priceWithTaxes: 0, targetPrice: 0 });
      return;
    }
    const res = await computeSkuPricingPreview({
      avgCost,
      markupVal: markup,
      taxesVal: taxes,
      interestVal: interest,
      markupKind,
      taxesKind,
      interestKind,
    });
    if (rid !== computeRequestIdRef.current) return;
    if (!res) {
      setPreview(null);
      return;
    }
    setPreview({
      priceBefore: res.price_before,
      priceWithTaxes: res.price_with_taxes,
      targetPrice: res.target,
    });
  }, [avgCost, selectedSku, markup, taxes, interest, markupKind, taxesKind, interestKind]);

  useEffect(() => {
    if (loadingInsight) return;
    const tid = window.setTimeout(() => {
      void scheduleComputePreview();
    }, 40);
    return () => window.clearTimeout(tid);
  }, [loadingInsight, scheduleComputePreview]);

  const loadInsight = useCallback(async (sku: string) => {
    if (!sku.trim()) {
      insightRequestIdRef.current += 1;
      setSnapshot(null);
      setRecords([]);
      setPrices([]);
      setPreview(null);
      setLoadingInsight(false);
      return;
    }
    const myId = ++insightRequestIdRef.current;
    setLoadingInsight(true);
    try {
      const { snap, rec, ph } = await loadPricingInsightBundleCached(sku);
      if (myId !== insightRequestIdRef.current) return;
      if (snap && snap.sku_master.sku.trim() !== sku.trim()) {
        setSnapshot(null);
        setRecords([]);
        setPrices([]);
        return;
      }
      setSnapshot(snap);
      setRecords(rec);
      setPrices(ph);
      if (snap && snap.sku_master.sku.trim() === sku.trim()) {
        const ap = snap.active_pricing;
        if (ap && ap.sku.trim() !== snap.sku_master.sku.trim()) {
          setMarkup(0);
          setTaxes(0);
          setInterest(0);
          setMarkupKind(0);
          setTaxesKind(0);
          setInterestKind(0);
        } else if (ap) {
          setMarkup(ap.markup_pct);
          setTaxes(ap.taxes_pct);
          setInterest(ap.interest_pct);
          setMarkupKind(ap.markup_kind === 1 ? 1 : 0);
          setTaxesKind(ap.taxes_kind === 1 ? 1 : 0);
          setInterestKind(ap.interest_kind === 1 ? 1 : 0);
        } else {
          setMarkup(0);
          setTaxes(0);
          setInterest(0);
          setMarkupKind(0);
          setTaxesKind(0);
          setInterestKind(0);
        }
      }
    } finally {
      if (myId === insightRequestIdRef.current) setLoadingInsight(false);
    }
  }, []);

  useEffect(() => {
    const tid = window.setTimeout(() => {
      void loadInsight(selectedSku);
    }, 40);
    return () => window.clearTimeout(tid);
  }, [selectedSku, loadInsight]);

  return (
    <form action={formAction} className="space-y-8">
      <input type="hidden" name="sku" value={selectedSku} />
      <SubmitRefetchBridge
        onIdle={() => {
          invalidatePricingInsightCache(selectedSku);
          void loadInsight(selectedSku);
        }}
      />

      <FormAlert state={displayState.message ? displayState : undefined} />

      {/* ============ CONTEXT BAR ============ */}
      <ContextBar
        rows={rows}
        pickByName={pickByName}
        pickMode={pickMode}
        setPickMode={setPickMode}
        selectedSku={selectedSku}
        setSelectedSku={setSelectedSku}
        nameLabelToSku={nameLabelToSku}
        avgCost={avgCost}
        currentPrice={currentPrice}
        stock={stock}
      />

      {/* CMP zero alert */}
      {avgCost <= 0 ? (
        <div
          className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] px-4 py-3 text-sm text-amber-200"
          role="alert"
        >
          <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-amber-500/40 text-[10px] font-bold">
            !
          </span>
          <span>
            Custo médio do estoque <strong className="text-amber-100">indisponível</strong> (CMP = 0). Dê entrada
            em <strong className="text-amber-100">Custos</strong> antes de precificar.
          </span>
        </div>
      ) : null}

      {/* ============ ENGINE ↔ DECISION ============ */}
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        {/* PRICING ENGINE */}
        <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
          <header className="border-b border-border/40 px-6 py-4">
            <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Pricing engine</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Configure margem, impostos e encargos. Cálculo em tempo real à direita.
            </p>
          </header>
          <div className="divide-y divide-border/30">
            <ParameterBlock
              label="Margem"
              hint="Quanto adicionar sobre o CMP para chegar ao preço pré-impostos."
              field="markup"
              value={markup}
              onValueChange={setMarkup}
              kind={markupKind}
              onKindChange={setMarkupKind}
            />
            <ParameterBlock
              label="Impostos"
              hint="Tributação aplicada sobre o preço pré-impostos."
              field="taxes"
              value={taxes}
              onValueChange={setTaxes}
              kind={taxesKind}
              onKindChange={setTaxesKind}
            />
            <ParameterBlock
              label="Encargos"
              hint="Juros, taxas de cartão ou ajustes finais sobre o preço com impostos."
              field="interest"
              value={interest}
              onValueChange={setInterest}
              kind={interestKind}
              onKindChange={setInterestKind}
            />
          </div>
        </section>

        {/* DECISION ZONE */}
        <DecisionZone
          priceBefore={displayPreview.priceBefore}
          priceWithTaxes={displayPreview.priceWithTaxes}
          targetPrice={displayPreview.targetPrice}
          currentPrice={currentPrice}
          targetVsCurrentPct={targetVsCurrentPct}
          canSave={canSave}
        />
      </div>

      {/* ============ INSIGHT TABS ============ */}
      <PricingInsightTabs
        loading={loadingInsight}
        selectedSku={selectedSku}
        snapshot={snapshot}
        records={records}
        prices={prices}
      />
    </form>
  );
}

function SubmitRefetchBridge({ onIdle }: { onIdle: () => void }) {
  const { pending } = useFormStatus();
  const prevPending = useRef(false);
  useEffect(() => {
    if (prevPending.current && !pending) {
      onIdle();
    }
    prevPending.current = pending;
  }, [pending, onIdle]);
  return null;
}

// ============ CONTEXT BAR ============

function ContextBar({
  rows,
  pickByName,
  pickMode,
  setPickMode,
  selectedSku,
  setSelectedSku,
  nameLabelToSku,
  avgCost,
  currentPrice,
  stock,
}: {
  rows: SkuMasterRow[];
  pickByName: SkuCostPickerOption[];
  pickMode: PickMode;
  setPickMode: (m: PickMode) => void;
  selectedSku: string;
  setSelectedSku: (s: string) => void;
  nameLabelToSku: Map<string, string>;
  avgCost: number;
  currentPrice: number;
  stock: number;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      <div className="grid gap-px bg-border/60 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* SKU picker */}
        <div className="bg-background px-6 py-5">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">SKU em foco</p>
            {pickByName.length > 0 ? (
              <div className="inline-flex items-center gap-0.5 rounded-lg border border-border/60 bg-background p-0.5">
                <label
                  className={cn(
                    "inline-flex h-6 cursor-pointer items-center rounded-md px-2.5 text-[11px] font-medium transition-colors",
                    pickMode === "sku" ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <input
                    type="radio"
                    name="_pick_mode_pricing"
                    checked={pickMode === "sku"}
                    onChange={() => setPickMode("sku")}
                    className="sr-only"
                  />
                  SKU
                </label>
                <label
                  className={cn(
                    "inline-flex h-6 cursor-pointer items-center rounded-md px-2.5 text-[11px] font-medium transition-colors",
                    pickMode === "name" ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <input
                    type="radio"
                    name="_pick_mode_pricing"
                    checked={pickMode === "name"}
                    onChange={() => setPickMode("name")}
                    className="sr-only"
                  />
                  Nome
                </label>
              </div>
            ) : null}
          </div>
          {pickMode === "sku" || !pickByName.length ? (
            <Select
              id="pricing_sku_select"
              value={selectedSku}
              onChange={(event) => setSelectedSku(event.target.value)}
              aria-label="Seleccionar SKU"
              className="h-12 font-mono text-sm"
            >
              {rows.length === 0 ? <option value="">Nenhum SKU cadastrado</option> : null}
              {rows.map((row) => (
                <option key={row.sku} value={row.sku}>
                  {row.sku} · CMP {formatCurrency(row.avgUnitCost)} · estoque {row.totalStock}
                </option>
              ))}
            </Select>
          ) : (
            <Select
              id="pricing_name_select"
              value={pickByName.find((o) => o.sku === selectedSku)?.label ?? pickByName[0]?.label ?? ""}
              onChange={(e) => {
                const sku = nameLabelToSku.get(e.target.value);
                if (sku) setSelectedSku(sku);
              }}
              aria-label="Seleccionar por nome"
              className="h-12"
            >
              {pickByName.map((o) => (
                <option key={o.sku} value={o.label}>
                  {o.label}
                </option>
              ))}
            </Select>
          )}
        </div>

        {/* Inline metrics */}
        <div className="grid grid-cols-3 divide-x divide-border/60 bg-background">
          <ContextMetric label="CMP atual" value={formatCurrency(avgCost)} />
          <ContextMetric label="Preço ativo" value={formatCurrency(currentPrice)} accent />
          <ContextMetric label="Estoque" value={String(stock)} mono />
        </div>
      </div>
    </section>
  );
}

function ContextMetric({
  label,
  value,
  accent,
  mono,
}: {
  label: string;
  value: string;
  accent?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="px-5 py-5">
      <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1.5 font-serif text-xl font-semibold tabular-nums tracking-tight",
          accent && "text-[#d4b36c]",
          mono && "font-mono text-lg"
        )}
      >
        {value}
      </p>
    </div>
  );
}

// ============ PARAMETER BLOCK ============

function ParameterBlock({
  label,
  hint,
  field,
  value,
  onValueChange,
  kind,
  onKindChange,
}: {
  label: string;
  hint: string;
  field: string;
  value: number;
  onValueChange: (value: number) => void;
  kind: 0 | 1;
  onKindChange: (kind: 0 | 1) => void;
}) {
  return (
    <div className="grid gap-5 px-6 py-5 sm:grid-cols-[1fr_minmax(0,9rem)_minmax(0,9rem)] sm:items-end">
      <div>
        <Label htmlFor={field} className="text-sm font-medium tracking-tight text-foreground">
          {label}
        </Label>
        <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{hint}</p>
      </div>
      <div className="space-y-1.5">
        <Label
          htmlFor={field}
          className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground"
        >
          Valor
        </Label>
        <div className="relative">
          <Input
            id={field}
            name={field}
            type="number"
            step="0.01"
            min={0}
            value={value}
            onChange={(event) => onValueChange(Number(event.target.value) || 0)}
            className="h-10 pr-9 font-mono tabular-nums"
          />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
            {kind === 0 ? "%" : "R$"}
          </span>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Modo</Label>
        <div className="inline-flex w-full items-center gap-0.5 rounded-lg border border-border/60 bg-background p-0.5">
          <ModeButton active={kind === 0} onClick={() => onKindChange(0)}>
            %
          </ModeButton>
          <ModeButton active={kind === 1} onClick={() => onKindChange(1)}>
            R$
          </ModeButton>
        </div>
        <input type="hidden" name={`${field}_kind`} value={kind} />
      </div>
    </div>
  );
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-7 flex-1 items-center justify-center rounded-md px-2 text-xs font-medium transition-colors",
        active ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

// ============ DECISION ZONE ============

function DecisionZone({
  priceBefore,
  priceWithTaxes,
  targetPrice,
  currentPrice,
  targetVsCurrentPct,
  canSave,
}: {
  priceBefore: number;
  priceWithTaxes: number;
  targetPrice: number;
  currentPrice: number;
  targetVsCurrentPct: number | null;
  canSave: boolean;
}) {
  const positive = (targetVsCurrentPct ?? 0) >= 0;
  const Arrow = positive ? ArrowUpRight : ArrowDownRight;

  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-[#c7a35b]/30 bg-gradient-to-br from-[#c7a35b]/[0.05] to-transparent">
      <header className="border-b border-border/40 px-6 py-4">
        <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Decisão · pipeline de preço</p>
        <p className="mt-1 text-xs text-muted-foreground">Cálculo em tempo real (mesmo motor que persiste).</p>
      </header>

      <div className="flex-1 space-y-5 px-6 py-6">
        <PipelineRow
          step="01"
          label="Pré-impostos"
          value={priceBefore}
          dim={priceBefore <= 0}
        />
        <PipelineConnector />
        <PipelineRow
          step="02"
          label="Com impostos"
          value={priceWithTaxes}
          dim={priceWithTaxes <= 0}
        />
        <PipelineConnector />
        <div className="rounded-xl border border-[#c7a35b]/40 bg-[#c7a35b]/[0.07] px-5 py-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-[#d4b36c]">★ Preço alvo</p>
          <p className="mt-2 font-serif text-4xl font-semibold tabular-nums tracking-tight md:text-5xl">
            {targetPrice > 0 ? formatCurrency(targetPrice) : "—"}
          </p>
          {targetVsCurrentPct != null ? (
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs">
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 tabular-nums",
                  positive ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"
                )}
              >
                <Arrow className="h-3 w-3" />
                {Math.abs(targetVsCurrentPct).toFixed(1)}%
              </span>
              <span className="text-muted-foreground">vs preço ativo</span>
            </p>
          ) : currentPrice > 0 ? (
            <p className="mt-2 text-[11px] text-muted-foreground">comparação indisponível</p>
          ) : null}
        </div>
      </div>

      <footer className="border-t border-border/40 bg-background/50 px-6 py-4">
        <SubmitButton disabled={!canSave} blockWhilePending={false} className="w-full justify-center">
          Salvar precificação
        </SubmitButton>
        {!canSave ? (
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            Preencha CMP &gt; 0 e gere um preço alvo para salvar.
          </p>
        ) : null}
      </footer>
    </section>
  );
}

function PipelineRow({
  step,
  label,
  value,
  dim,
}: {
  step: string;
  label: string;
  value: number;
  dim?: boolean;
}) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4 transition-opacity", dim && "opacity-50")}>
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{step}</span>
        <span className="text-sm text-foreground">{label}</span>
      </div>
      <span className="font-serif text-lg font-medium tabular-nums tracking-tight">
        {value > 0 ? formatCurrency(value) : "—"}
      </span>
    </div>
  );
}

function PipelineConnector() {
  return (
    <div className="flex justify-center" aria-hidden>
      <ArrowDown className="h-3 w-3 text-muted-foreground/50" />
    </div>
  );
}

// ============ INSIGHT TABS ============

type InsightTab = "active" | "workflow" | "price";

function PricingInsightTabs({
  loading,
  selectedSku,
  snapshot,
  records,
  prices,
}: {
  loading: boolean;
  selectedSku: string;
  snapshot: PricingSnapshotApi | null;
  records: PricingRecordApiRow[];
  prices: PriceHistoryApiRow[];
}) {
  const [tab, setTab] = useState<InsightTab>("active");
  const ap = snapshot?.active_pricing;
  const sm = snapshot?.sku_master;
  const apConsistent = Boolean(ap && sm && ap.sku.trim() === sm.sku.trim());

  const tabs: { id: InsightTab; label: string; count?: number }[] = [
    { id: "active", label: "Activo" },
    { id: "workflow", label: "Histórico workflow", count: records.length },
    { id: "price", label: "Histórico preço", count: prices.length },
  ];

  const smSku = snapshot?.sku_master?.sku?.trim() ?? "";
  const staleWhileLoading = Boolean(
    loading && smSku && selectedSku.trim() && smSku !== selectedSku.trim()
  );

  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border/40 px-6 py-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <p className="text-[10px] uppercase tracking-[0.28em] text-[#d4b36c]">Histórico &amp; referência</p>
          {loading ? (
            <span className="text-[10px] text-muted-foreground" aria-live="polite">
              A sincronizar…
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-0.5 rounded-lg border border-border/60 bg-background p-0.5">
          {tabs.map((t) => (
            <button
              type="button"
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors",
                tab === t.id ? "bg-muted/60 text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t.label}
              {typeof t.count === "number" && t.count > 0 ? (
                <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{t.count}</span>
              ) : null}
            </button>
          ))}
        </div>
      </header>

      <div className={cn("relative px-6 py-5", loading && "opacity-[0.94]")}>
        {staleWhileLoading ? (
          <p className="mb-3 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
            A actualizar painel para <span className="font-mono">{selectedSku}</span>…
          </p>
        ) : null}
        {loading && !snapshot && records.length === 0 && prices.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">A carregar…</p>
        ) : tab === "active" ? (
          <ActivePane sm={sm ?? null} ap={ap ?? null} apConsistent={apConsistent} />
        ) : tab === "workflow" ? (
          <WorkflowHistoryTable records={records} />
        ) : (
          <PriceHistoryTable prices={prices} />
        )}
      </div>
    </section>
  );
}

function ActivePane({
  sm,
  ap,
  apConsistent,
}: {
  sm: PricingSnapshotApi["sku_master"] | null;
  ap: PricingSnapshotApi["active_pricing"] | null;
  apConsistent: boolean;
}) {
  if (!sm) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Sem dados.</p>;
  }
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div>
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">sku_master</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
          <DefRow label="CMP médio" value={formatCurrency(sm.avg_unit_cost)} />
          <DefRow label="Preço venda" value={formatCurrency(sm.selling_price)} accent />
          <DefRow label="Custo estruturado" value={formatCurrency(sm.structured_cost_total)} />
          <DefRow label="Stock total" value={String(sm.total_stock)} mono />
          <DefRow label="Actualizado" value={formatDate(sm.updated_at)} muted />
        </dl>
      </div>
      <div>
        <p className="mb-3 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Workflow activo</p>
        {!apConsistent || !ap ? (
          <p className="text-sm text-muted-foreground">
            {ap && !apConsistent
              ? "Registo activo inconsistente com o mestre; não é exibido."
              : "Nenhum registo de workflow activo para este SKU."}
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
            <DefRow label="ID" value={String(ap.id)} mono />
            <DefRow label="CMP snapshot" value={formatCurrency(ap.avg_cost_snapshot)} />
            <dt className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Markup / Taxas / Juros</dt>
            <dd className="font-mono text-xs tabular-nums">
              {ap.markup_pct}
              {kindLabel(ap.markup_kind)} · {ap.taxes_pct}
              {kindLabel(ap.taxes_kind)} · {ap.interest_pct}
              {kindLabel(ap.interest_kind)}
            </dd>
            <dt className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Pré / c/ imp / alvo</dt>
            <dd className="font-mono text-xs tabular-nums">
              {formatCurrency(ap.price_before_taxes)} · {formatCurrency(ap.price_with_taxes)} ·{" "}
              <span className="text-[#d4b36c]">{formatCurrency(ap.target_price)}</span>
            </dd>
            <DefRow label="Criado" value={formatDate(ap.created_at)} muted />
          </dl>
        )}
      </div>
    </div>
  );
}

function DefRow({
  label,
  value,
  accent,
  mono,
  muted,
}: {
  label: string;
  value: string;
  accent?: boolean;
  mono?: boolean;
  muted?: boolean;
}) {
  return (
    <>
      <dt className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "tabular-nums",
          mono && "font-mono text-xs",
          accent && "text-[#d4b36c] font-medium",
          muted && "text-muted-foreground text-xs"
        )}
      >
        {value}
      </dd>
    </>
  );
}

function WorkflowHistoryTable({ records }: { records: PricingRecordApiRow[] }) {
  if (records.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Sem histórico de workflow.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="[&_th]:text-[10px] [&_th]:uppercase [&_th]:tracking-[0.16em] [&_th]:text-muted-foreground">
            <TableHead>ID</TableHead>
            <TableHead>Activo</TableHead>
            <TableHead>CMP snap.</TableHead>
            <TableHead>Markup</TableHead>
            <TableHead>Taxas</TableHead>
            <TableHead>Juros</TableHead>
            <TableHead>Pré-imp.</TableHead>
            <TableHead>C/ imp.</TableHead>
            <TableHead>Alvo</TableHead>
            <TableHead>Criado</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {records.map((r) => (
            <TableRow key={r.id} className="border-b-border/30">
              <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">{r.id}</TableCell>
              <TableCell>
                {r.is_active ? (
                  <Badge variant="gold">Sim</Badge>
                ) : (
                  <span className="text-xs text-muted-foreground">Não</span>
                )}
              </TableCell>
              <TableCell className="text-xs tabular-nums">{formatCurrency(r.avg_cost_snapshot)}</TableCell>
              <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                {r.markup_pct}
                {kindLabel(r.markup_kind)}
              </TableCell>
              <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                {r.taxes_pct}
                {kindLabel(r.taxes_kind)}
              </TableCell>
              <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                {r.interest_pct}
                {kindLabel(r.interest_kind)}
              </TableCell>
              <TableCell className="text-xs tabular-nums">{formatCurrency(r.price_before_taxes)}</TableCell>
              <TableCell className="text-xs tabular-nums">{formatCurrency(r.price_with_taxes)}</TableCell>
              <TableCell className="text-xs tabular-nums font-medium text-[#d4b36c]">
                {formatCurrency(r.target_price)}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">{formatDate(r.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function PriceHistoryTable({ prices }: { prices: PriceHistoryApiRow[] }) {
  if (prices.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Sem entradas de histórico de preço.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="[&_th]:text-[10px] [&_th]:uppercase [&_th]:tracking-[0.16em] [&_th]:text-muted-foreground">
            <TableHead>ID</TableHead>
            <TableHead>Preço anterior</TableHead>
            <TableHead>Preço novo</TableHead>
            <TableHead>Δ</TableHead>
            <TableHead>Data</TableHead>
            <TableHead>Nota</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {prices.map((h) => {
            const old = h.old_price == null ? null : Number(h.old_price);
            const next = Number(h.new_price);
            const delta = old != null && old > 0 ? ((next - old) / old) * 100 : null;
            const positive = (delta ?? 0) >= 0;
            return (
              <TableRow key={h.id} className="border-b-border/30">
                <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">{h.id}</TableCell>
                <TableCell className="text-xs tabular-nums text-muted-foreground">
                  {old == null ? "—" : formatCurrency(old)}
                </TableCell>
                <TableCell className="text-sm tabular-nums font-medium">{formatCurrency(next)}</TableCell>
                <TableCell>
                  {delta != null ? (
                    <span
                      className={cn(
                        "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] tabular-nums",
                        positive ? "bg-emerald-500/10 text-emerald-300" : "bg-destructive/10 text-destructive"
                      )}
                    >
                      {positive ? "↑" : "↓"} {Math.abs(delta).toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{formatDate(h.created_at)}</TableCell>
                <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">
                  {h.note || "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
