import { NewCustomerForm } from "./new-customer-form";
import { PageHero } from "@/components/page-hero";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function NewCustomerPage() {
  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="CRM"
        title="Novo cliente"
        description="Busca por CEP via ViaCEP e alocação sequencial do `customer_code`, equivalente a `services.customer_service.insert_customer_row`."
      />
      <Card>
        <CardHeader>
          <CardTitle>Dados do cliente</CardTitle>
          <CardDescription>Campos obrigatórios marcados com *.</CardDescription>
        </CardHeader>
        <CardContent>
          <NewCustomerForm />
        </CardContent>
      </Card>
    </div>
  );
}
