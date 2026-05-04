import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type KpiCardProps = {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  highlight?: boolean;
  /** Ex.: "+12,4% vs período ant." ou "+1,2 p.p." */
  delta?: string | null;
};

export function KpiCard({ title, value, detail, icon: Icon, highlight, delta }: KpiCardProps) {
  const deltaTone =
    delta == null
      ? ""
      : delta.startsWith("+")
        ? "text-emerald-400/90"
        : delta.startsWith("−") || delta.startsWith("-")
          ? "text-rose-400/90"
          : "text-muted-foreground";

  return (
    <Card className={cn("overflow-hidden", highlight && "border-[#c7a35b]/60 bg-[#c7a35b]/12")}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{title}</p>
            <p className="mt-4 font-serif text-3xl font-semibold tracking-tight">{value}</p>
            {delta ? (
              <p className={cn("mt-1 text-xs font-medium tabular-nums", deltaTone)}>{delta}</p>
            ) : null}
            <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
          </div>
          <span className="shrink-0 rounded-full border border-white/10 bg-white/5 p-2 text-[#d4b36c]">
            <Icon className="h-4 w-4" />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
