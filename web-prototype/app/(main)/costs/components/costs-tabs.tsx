"use client";

import { useState, type ReactNode } from "react";
import { Layers, PackagePlus } from "lucide-react";
import { cn } from "@/lib/utils";

export function CostsTabs({
  composition,
  stockEntry,
}: {
  composition: ReactNode;
  stockEntry: ReactNode;
}) {
  const [tab, setTab] = useState<"composition" | "stock">("composition");

  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-background">
      <div className="flex items-center gap-0.5 border-b border-border/60 px-2 py-2">
        <TabButton
          active={tab === "composition"}
          onClick={() => setTab("composition")}
          icon={<Layers className="h-3.5 w-3.5" />}
          label="Composição de custo"
          hint="custo unitário planejado por SKU"
        />
        <TabButton
          active={tab === "stock"}
          onClick={() => setTab("stock")}
          icon={<PackagePlus className="h-3.5 w-3.5" />}
          label="Entrada de estoque"
          hint="recalcula CMP por média ponderada"
        />
      </div>
      {/* Both panels stay mounted to preserve internal state and avoid re-fetching */}
      <div className={cn("p-6 md:p-8", tab !== "composition" && "hidden")}>{composition}</div>
      <div className={cn("p-6 md:p-8", tab !== "stock" && "hidden")}>{stockEntry}</div>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative inline-flex flex-col items-start gap-0.5 rounded-lg px-4 py-2 text-left transition-colors",
        active ? "bg-muted/50 text-foreground" : "text-muted-foreground hover:bg-muted/30 hover:text-foreground"
      )}
    >
      <span className="inline-flex items-center gap-2 text-sm font-medium tracking-tight">
        <span className={active ? "text-[#d4b36c]" : ""}>{icon}</span>
        {label}
      </span>
      <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{hint}</span>
    </button>
  );
}
