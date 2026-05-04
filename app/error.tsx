"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <Card className="mx-auto mt-16 max-w-xl">
      <CardHeader>
        <CardTitle>Algo saiu do script.</CardTitle>
        <CardDescription>
          Não foi possível concluir esta operação. Os dados não foram alterados.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <code className="block overflow-x-auto rounded-xl bg-muted p-3 text-xs text-muted-foreground">
          {error.message}
          {error.digest ? ` · ${error.digest}` : null}
        </code>
        <Button variant="luxury" onClick={() => reset()}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
