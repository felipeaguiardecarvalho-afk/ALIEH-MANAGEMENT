// Visual-only filter strip. Real date-range/SKU filtering requires extending
// lib/queries.ts (currently fixed at 30d) and is intentionally out of scope here.
import { Calendar } from "lucide-react";

export function PeriodFilter() {
  const periods = [
    { id: "7d", label: "7d" },
    { id: "30d", label: "30 dias", active: true },
    { id: "90d", label: "90d" },
    { id: "ytd", label: "Ano" },
  ];
  return (
    <div className="flex items-center gap-2">
      <div className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-background/60 px-1 py-0.5 text-xs">
        <Calendar className="ml-1.5 h-3 w-3 text-muted-foreground" />
        {periods.map((p) => (
          <span
            key={p.id}
            aria-disabled={!p.active}
            className={`inline-flex h-7 items-center rounded-full px-3 transition-colors ${
              p.active
                ? "bg-foreground text-background"
                : "text-muted-foreground/60"
            }`}
          >
            {p.label}
          </span>
        ))}
      </div>
      <span className="hidden text-[10px] uppercase tracking-[0.18em] text-muted-foreground md:inline">
        janela fixa · cache 120s
      </span>
    </div>
  );
}
