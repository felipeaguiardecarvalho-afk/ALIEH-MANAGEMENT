"use client";

import Link from "next/link";
import { useActionState, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { FormAlert, SubmitButton } from "@/components/form-status";
import { AttributeSelectWithOther } from "@/components/attribute-select-with-other";
import { ActionSuccessToast } from "@/components/action-success-toast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createProduct,
  previewProductSkuBodyAction,
  type ProductFormState,
} from "@/lib/actions/products";
import { ProductImageUpload } from "@/components/product-image-upload";
import { ProductPreviewCard } from "@/components/product-preview-card";
import type { ProductAttributeOptions } from "@/lib/products-api";

const initialState: ProductFormState = { ok: false, message: "" };

type AttrKey = "frame_color" | "lens_color" | "gender" | "palette" | "style";

const STEPS = [
  { id: 1, label: "Identidade", hint: "Nome e data" },
  { id: 2, label: "Atributos", hint: "Armação, lente, estilo" },
  { id: 3, label: "Imagem", hint: "Foto do lote" },
  { id: 4, label: "Revisão", hint: "Confirmar e cadastrar" },
] as const;

export function NewProductForm({
  attributeOptions,
  isAdmin,
}: {
  attributeOptions: ProductAttributeOptions;
  isAdmin: boolean;
}) {
  // ───── Logic preserved verbatim ─────
  const [state, formAction] = useActionState(createProduct, initialState);
  const [name, setName] = useState("");
  const [attrs, setAttrs] = useState<Record<AttrKey, string>>({
    frame_color: "",
    lens_color: "",
    gender: "",
    palette: "",
    style: "",
  });
  const [previewSku, setPreviewSku] = useState<string | null>(null);
  const [registeredDate, setRegisteredDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [formEpoch, setFormEpoch] = useState(0);
  const [imageReset, setImageReset] = useState(0);
  const [toastOpen, setToastOpen] = useState(false);
  const lastSig = useRef("");

  const onAttr = useCallback((key: AttrKey) => (value: string) => {
    setAttrs((prev) => ({ ...prev, [key]: value }));
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      void previewProductSkuBodyAction({
        name,
        frame_color: attrs.frame_color,
        lens_color: attrs.lens_color,
        gender: attrs.gender,
        palette: attrs.palette,
        style: attrs.style,
      }).then((r) => setPreviewSku(r.preview));
    }, 300);
    return () => clearTimeout(t);
  }, [name, attrs]);

  useEffect(() => {
    if (!state.ok) {
      lastSig.current = "";
      return;
    }
    if (!state.message) return;
    const sig = `${state.ok}:${state.message}`;
    if (sig === lastSig.current) return;
    lastSig.current = sig;
    setToastOpen(true);
    setName("");
    setAttrs({ frame_color: "", lens_color: "", gender: "", palette: "", style: "" });
    setPreviewSku(null);
    setRegisteredDate(new Date().toISOString().slice(0, 10));
    setFormEpoch((n) => n + 1);
    setImageReset((n) => n + 1);
    setStep(1);
  }, [state]);

  // ───── Visual-only step state ─────
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const goNext = () => setStep((s) => (s < 4 ? ((s + 1) as 1 | 2 | 3 | 4) : s));
  const goBack = () => setStep((s) => (s > 1 ? ((s - 1) as 1 | 2 | 3 | 4) : s));

  const filledAttrs = Object.values(attrs).filter((v) => v.trim()).length;
  const canAdvanceFrom1 = name.trim().length > 0 && registeredDate.length > 0;
  const canAdvanceFrom2 = filledAttrs === 5;

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_360px]">
      <form action={formAction} className="min-w-0 space-y-10">
        <ActionSuccessToast
          message={state.ok && state.message ? state.message : ""}
          visible={toastOpen && Boolean(state.ok && state.message)}
          onDismiss={() => setToastOpen(false)}
          durationMs={4500}
        />

        {/* Stepper */}
        <ol className="flex items-center gap-2">
          {STEPS.map((s, i) => {
            const active = step === s.id;
            const done = step > s.id;
            return (
              <li key={s.id} className="flex flex-1 items-center gap-2 first:flex-none">
                <button
                  type="button"
                  onClick={() => setStep(s.id as 1 | 2 | 3 | 4)}
                  className={`group flex items-center gap-2.5 rounded-full border px-3 py-1.5 text-xs transition-all duration-200 ${
                    active
                      ? "border-[#c7a35b]/50 bg-[#c7a35b]/10 text-foreground"
                      : done
                        ? "border-border/60 bg-background text-muted-foreground hover:text-foreground"
                        : "border-border/40 bg-transparent text-muted-foreground"
                  }`}
                >
                  <span
                    className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold tabular-nums transition-colors ${
                      done
                        ? "bg-[#c7a35b] text-black"
                        : active
                          ? "bg-foreground text-background"
                          : "bg-muted/40 text-muted-foreground"
                    }`}
                  >
                    {done ? <Check className="h-3 w-3" /> : s.id}
                  </span>
                  <span className="font-medium">{s.label}</span>
                  <span className="hidden text-muted-foreground/70 md:inline">· {s.hint}</span>
                </button>
                {i < STEPS.length - 1 ? (
                  <span className={`hidden h-px flex-1 transition-colors duration-300 md:block ${
                    done ? "bg-[#c7a35b]/40" : "bg-border/50"
                  }`} />
                ) : null}
              </li>
            );
          })}
        </ol>

        <FormAlert state={!state.ok && state.message ? state : undefined} />

        {/* Step 1 — Identity */}
        <section className={step === 1 ? "" : "hidden"} aria-hidden={step !== 1}>
          <header className="mb-6 space-y-1.5">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Etapa 1 de 4</p>
            <h2 className="font-serif text-3xl font-semibold tracking-tight">Identidade do lote</h2>
            <p className="text-sm text-muted-foreground">
              Nome do produto e data de registo. O SKU será gerado dos atributos na próxima etapa.
            </p>
          </header>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name" className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Nome do produto *
              </Label>
              <Input
                id="name"
                name="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoComplete="off"
                placeholder="Ex.: Aviator Gold"
                className="h-12 border-0 border-b border-border/60 bg-transparent px-0 font-serif text-xl tracking-tight shadow-none transition-colors focus-visible:border-[#c7a35b]/60 focus-visible:ring-0"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="registered_date" className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Data de registo
              </Label>
              <Input
                id="registered_date"
                name="registered_date"
                type="date"
                value={registeredDate}
                onChange={(e) => setRegisteredDate(e.target.value)}
                required
                className="h-12 border-0 border-b border-border/60 bg-transparent px-0 font-serif text-xl tabular-nums tracking-tight shadow-none focus-visible:border-[#c7a35b]/60 focus-visible:ring-0"
              />
            </div>
          </div>
        </section>

        {/* Step 2 — Attributes */}
        <section className={step === 2 ? "" : "hidden"} aria-hidden={step !== 2}>
          <header className="mb-6 space-y-1.5">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Etapa 2 de 4</p>
            <h2 className="font-serif text-3xl font-semibold tracking-tight">Atributos</h2>
            <p className="text-sm text-muted-foreground">
              Cinco dimensões que definem o lote. Pode escolher &quot;Outro…&quot; e escrever livremente.
            </p>
          </header>
          <div className="grid gap-5 md:grid-cols-2">
            <AttributeSelectWithOther key={`fc-${formEpoch}`} name="frame_color" label="Cor da armação" presetOptions={attributeOptions.frame_color} emptyLabel="— selecionar —" onResolvedChange={onAttr("frame_color")} />
            <AttributeSelectWithOther key={`lc-${formEpoch}`} name="lens_color"  label="Cor da lente"  presetOptions={attributeOptions.lens_color}  emptyLabel="— selecionar —" onResolvedChange={onAttr("lens_color")} />
            <AttributeSelectWithOther key={`ge-${formEpoch}`} name="gender"      label="Gênero"        presetOptions={attributeOptions.gender}      emptyLabel="— selecionar —" onResolvedChange={onAttr("gender")} />
            <AttributeSelectWithOther key={`pa-${formEpoch}`} name="palette"     label="Paleta"        presetOptions={attributeOptions.palette}     emptyLabel="— selecionar —" onResolvedChange={onAttr("palette")} />
            <AttributeSelectWithOther key={`st-${formEpoch}`} name="style"       label="Estilo"        presetOptions={attributeOptions.style}       emptyLabel="— selecionar —" onResolvedChange={onAttr("style")} />
          </div>
          {previewSku ? (
            <div className="mt-6 rounded-xl border border-[#c7a35b]/35 bg-[#c7a35b]/[0.08] px-5 py-4">
              <p className="text-[11px] uppercase tracking-[0.24em] text-[#d4b36c]">SKU gerado · só leitura</p>
              <p className="mt-1.5 font-mono text-2xl tracking-wide text-foreground">{previewSku}</p>
              <p className="mt-2 text-xs text-muted-foreground">Derivado do nome + atributos. Não é editável manualmente.</p>
            </div>
          ) : (
            <p className="mt-6 text-xs text-muted-foreground">
              Selecione todos os atributos para visualizar o SKU.
            </p>
          )}
        </section>

        {/* Step 3 — Image */}
        <section className={step === 3 ? "" : "hidden"} aria-hidden={step !== 3}>
          <header className="mb-6 space-y-1.5">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Etapa 3 de 4</p>
            <h2 className="font-serif text-3xl font-semibold tracking-tight">Imagem</h2>
            <p className="text-sm text-muted-foreground">
              Opcional. Pode adicionar agora ou mais tarde no detalhe do produto.
            </p>
          </header>
          <ProductImageUpload resetNonce={imageReset} />

          {isAdmin ? (
            <details className="mt-4 rounded-xl border border-border/60 bg-muted/10 p-4 text-sm">
              <summary className="cursor-pointer font-medium text-foreground">
                Sem Supabase: enviar imagem via API (disco)
              </summary>
              <p className="mt-2 text-xs text-muted-foreground">
                O ficheiro é lido no servidor Next e enviado em base64 para a api-prototype. Se já usou o upload para
                Storage acima, esse URL tem prioridade sobre este ficheiro.
              </p>
              <div className="mt-3 space-y-2">
                <Label htmlFor="product_image_file_direct">Ficheiro local (opcional)</Label>
                <Input
                  id="product_image_file_direct"
                  name="product_image_file"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                />
              </div>
            </details>
          ) : null}
        </section>

        {/* Step 4 — Review */}
        <section className={step === 4 ? "" : "hidden"} aria-hidden={step !== 4}>
          <header className="mb-6 space-y-1.5">
            <p className="text-[11px] uppercase tracking-[0.32em] text-[#d4b36c]">Etapa 4 de 4</p>
            <h2 className="font-serif text-3xl font-semibold tracking-tight">Revisão</h2>
            <p className="text-sm text-muted-foreground">
              Confira antes de cadastrar. O cadastro é bloqueado se já existir lote idêntico (mesmo nome+data+atributos) ou SKU.
            </p>
          </header>
          <dl className="grid gap-x-8 gap-y-5 md:grid-cols-2">
            <ReviewRow label="Nome" value={name || "—"} large />
            <ReviewRow label="Data de registo" value={registeredDate || "—"} mono />
            <ReviewRow label="SKU" value={previewSku ?? "—"} mono accent />
            <div className="md:col-span-2">
              <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Atributos</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(["frame_color", "lens_color", "gender", "palette", "style"] as const).map((k) =>
                  attrs[k] ? <Badge key={k} variant="secondary">{attrs[k]}</Badge> : (
                    <span key={k} className="inline-flex h-6 items-center rounded-full border border-dashed border-border/60 px-2.5 text-[10px] uppercase tracking-[0.14em] text-muted-foreground/60">
                      {k.replace("_", " ")} pendente
                    </span>
                  )
                )}
              </div>
            </div>
          </dl>

          {!isAdmin ? (
            <p className="mt-6 text-sm text-muted-foreground">
              Apenas o perfil <strong className="text-foreground">administrador</strong> pode cadastrar produtos
              (paridade com Streamlit).
            </p>
          ) : null}
        </section>

        {/* Footer nav */}
        <div className="flex items-center justify-between border-t border-border/40 pt-6">
          <div className="flex items-center gap-2">
            {step > 1 ? (
              <Button type="button" variant="ghost" onClick={goBack} className="gap-1.5">
                <ArrowLeft className="h-3.5 w-3.5" /> Voltar
              </Button>
            ) : (
              <Button type="button" variant="ghost" asChild className="gap-1.5 text-muted-foreground">
                <Link href="/products">
                  <ArrowLeft className="h-3.5 w-3.5" /> Cancelar
                </Link>
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-[11px] uppercase tracking-[0.18em] text-muted-foreground sm:inline">
              {step}/4
            </span>
            {step < 4 ? (
              <Button
                type="button"
                variant="luxury"
                onClick={goNext}
                disabled={(step === 1 && !canAdvanceFrom1) || (step === 2 && !canAdvanceFrom2)}
                className="gap-1.5"
              >
                Continuar <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <SubmitButton disabled={!isAdmin}>Cadastrar produto</SubmitButton>
            )}
          </div>
        </div>
      </form>

      {/* Sticky live preview */}
      <aside className="lg:sticky lg:top-24 lg:self-start">
        <p className="mb-3 text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Preview ao vivo</p>
        <ProductPreviewCard
          name={name}
          sku={previewSku}
          attrs={attrs}
          registeredDate={registeredDate}
        />
      </aside>
    </div>
  );
}

function ReviewRow({
  label,
  value,
  mono,
  large,
  accent,
}: {
  label: string;
  value: string;
  mono?: boolean;
  large?: boolean;
  accent?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">{label}</dt>
      <dd
        className={`mt-1 ${mono ? "font-mono" : "font-serif"} ${
          large ? "text-2xl tracking-tight" : "text-base"
        } ${accent ? "text-[#d4b36c]" : "text-foreground"}`}
      >
        {value}
      </dd>
    </div>
  );
}
