import { NextResponse } from "next/server";
import { getBatchesForSku } from "@/lib/queries";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const sku = searchParams.get("sku")?.trim();
  if (!sku) return NextResponse.json({ batches: [] });
  const batches = await getBatchesForSku(sku);
  return NextResponse.json({ batches });
}
