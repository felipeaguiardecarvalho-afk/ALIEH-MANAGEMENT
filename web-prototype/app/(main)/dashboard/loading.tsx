import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-10 pb-16">
      <div className="space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-12 w-80" />
        <Skeleton className="h-4 w-[60%]" />
      </div>
      <Skeleton className="h-[280px] w-full rounded-2xl" />
      <Skeleton className="h-3 w-64" />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-36 rounded-2xl" />
      <Skeleton className="h-24 rounded-2xl" />
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Skeleton className="h-[360px] rounded-2xl" />
        <Skeleton className="h-[360px] rounded-2xl" />
      </div>
    </div>
  );
}
