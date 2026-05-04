import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type KpiCardProps = {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  highlight?: boolean;
};

export function KpiCard({ title, value, detail, icon: Icon, highlight }: KpiCardProps) {
  return (
    <Card className={cn("overflow-hidden", highlight && "border-[#c7a35b]/50 bg-[#c7a35b]/10")}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{title}</p>
            <p className="mt-4 font-serif text-3xl font-semibold tracking-tight">{value}</p>
            <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
          </div>
          <span className="rounded-full border border-white/10 bg-white/5 p-2 text-[#d4b36c]">
            <Icon className="h-4 w-4" />
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
