import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-28" />
      {Array.from({ length: 5 }).map((_, index) => (
        <Skeleton key={index} className="h-40" />
      ))}
    </div>
  );
}
