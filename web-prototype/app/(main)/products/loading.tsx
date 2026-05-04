import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-4 w-[60%]" />
      </div>
      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border/60 bg-border/60 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-2 bg-background p-5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-24" />
          </div>
        ))}
      </div>
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 rounded-xl border border-border/60 bg-background/60 p-3">
        <Skeleton className="h-10 flex-1 min-w-[240px]" />
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-24" />
      </div>
      {/* Table rows */}
      <div className="overflow-hidden rounded-xl border border-border/60">
        <Skeleton className="h-11 w-full rounded-none" />
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 border-t border-border/60 px-4 py-3">
            <Skeleton className="h-4 w-10" />
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-4 flex-1 max-w-[200px]" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="ml-auto h-4 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}
