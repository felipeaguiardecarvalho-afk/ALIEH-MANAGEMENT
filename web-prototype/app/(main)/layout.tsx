import { ClientDataProvider } from "@/components/client-data-provider";
import { TopNav } from "@/components/top-nav";

export default function MainLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClientDataProvider>
      <TopNav />
      <main className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
    </ClientDataProvider>
  );
}
