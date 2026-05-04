import { Badge } from "@/components/ui/badge";

function monogram(sku: string | null | undefined, name: string) {
  const s = (sku ?? "").trim();
  if (s) return s.split("-")[0]?.slice(0, 4).toUpperCase() || s.slice(0, 4).toUpperCase();
  const w = name.trim().split(/\s+/);
  return ((w[0]?.[0] ?? "") + (w[1]?.[0] ?? "")).toUpperCase() || "—";
}

export function ProductPreviewCard({
  name,
  sku,
  attrs,
  registeredDate,
}: {
  name: string;
  sku: string | null;
  attrs: { frame_color?: string; lens_color?: string; gender?: string; palette?: string; style?: string };
  registeredDate?: string;
}) {
  const filled = Object.values(attrs).filter((v) => v && String(v).trim()).length;
  const totalAttrs = 5;
  const completion = Math.min(
    100,
    Math.round(
      ((name.trim() ? 1 : 0) * 30 + (filled / totalAttrs) * 60 + (sku ? 10 : 0))
    )
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      {/* Visual */}
      <div className="relative aspect-[4/3] overflow-hidden bg-gradient-to-br from-muted/30 via-background to-muted/5">
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-serif text-7xl font-semibold tracking-tight text-foreground/15">
            {monogram(sku, name || "Novo")}
          </span>
        </div>
        <div className="absolute left-4 top-4">
          <span className="inline-flex items-center gap-1 rounded-full bg-background/85 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground backdrop-blur">
            preview
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="space-y-4 p-5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.24em] text-[#d4b36c]">SKU gerado</p>
          <p className="mt-1 font-mono text-sm text-foreground">
            {sku ? sku : <span className="text-muted-foreground">—</span>}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Nome</p>
          <p className="mt-1 line-clamp-2 font-serif text-lg leading-tight tracking-tight">
            {name.trim() || <span className="text-muted-foreground">Por preencher</span>}
          </p>
        </div>

        {/* Attribute pills */}
        <div className="flex flex-wrap gap-1.5">
          {(["frame_color", "lens_color", "gender", "palette", "style"] as const).map((k) => {
            const v = (attrs[k] ?? "").trim();
            return v ? (
              <Badge key={k} variant="secondary" className="text-[11px]">
                {v}
              </Badge>
            ) : (
              <span
                key={k}
                className="inline-flex h-5 items-center rounded-full border border-dashed border-border/60 px-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground/60"
              >
                {labelFor(k)}
              </span>
            );
          })}
        </div>

        {registeredDate ? (
          <p className="border-t border-border/40 pt-3 text-[11px] text-muted-foreground">
            registado em <span className="text-foreground tabular-nums">{registeredDate}</span>
          </p>
        ) : null}

        {/* Completion */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            <span>Completo</span>
            <span className="tabular-nums text-foreground">{completion}%</span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-muted/40">
            <div
              className="h-full rounded-full bg-[#c7a35b] transition-[width] duration-300 ease-out"
              style={{ width: `${completion}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function labelFor(k: string) {
  const m: Record<string, string> = {
    frame_color: "Armação",
    lens_color: "Lente",
    gender: "Gênero",
    palette: "Paleta",
    style: "Estilo",
  };
  return m[k] ?? k;
}
