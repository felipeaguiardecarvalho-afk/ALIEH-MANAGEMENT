import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-28" />
      <Skeleton className="h-[420px]" />
      <Skeleton className="h-[280px]" />
      <Skeleton className="h-[320px]" />
      <Skeleton className="h-[360px]" />
    </div>
  );
}
