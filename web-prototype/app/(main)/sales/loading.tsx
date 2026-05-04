import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-28" />
      <Skeleton className="h-[460px]" />
    </div>
  );
}
