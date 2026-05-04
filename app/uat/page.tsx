import { PageHero } from "@/components/page-hero";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { UAT_MANUAL_CASES, UAT_STATUS_LABELS } from "@/lib/domain";
import { getUatRecords } from "@/lib/queries";
import { UatCaseCard } from "./uat-case-card";

export const dynamic = "force-dynamic";

export default async function UatPage() {
  const records = await getUatRecords();
  const byId = new Map(records.map((record) => [record.testId, record]));
  const done = records.filter((record) => record.status !== "pending").length;
  const total = UAT_MANUAL_CASES.length;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Qualidade"
        title="Checklist UAT"
        description="Casos manuais em `uat_manual_checklist`. Equivalente a `_render_uat_manual_checklist_page`."
      />

      <Card>
        <CardHeader>
          <CardTitle>Progresso</CardTitle>
          <CardDescription>
            {done} de {total} casos com resultado registrado.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-[#c7a35b]" style={{ width: `${progress}%` }} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        {UAT_MANUAL_CASES.map((testCase) => {
          const record = byId.get(testCase.code);
          return (
            <UatCaseCard
              key={testCase.code}
              code={testCase.code}
              title={testCase.title}
              description={testCase.description}
              currentStatus={(record?.status as keyof typeof UAT_STATUS_LABELS) ?? "pending"}
              currentNotes={record?.notes ?? ""}
              lastUpdatedAt={record?.updatedAt ?? record?.resultRecordedAt ?? null}
              lastUser={record?.recordedByUsername ?? null}
            />
          );
        })}
      </div>
    </div>
  );
}
