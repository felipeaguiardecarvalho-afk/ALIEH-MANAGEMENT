import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-28" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-[480px]" />
        <Skeleton className="h-[480px]" />
      </div>
      <Skeleton className="h-[360px]" />
    </div>
  );
}
