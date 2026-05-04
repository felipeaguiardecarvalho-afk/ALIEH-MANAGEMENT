"use server";

import { revalidatePath } from "next/cache";
import { apiPrototypeFetch, gateMutation, hasPrototypeApiUrl, readApiError } from "@/lib/api-prototype";
import { requireAdmin } from "@/lib/rbac";

export type ProductFormState = { ok: boolean; message: string };

export type LotActionState = { ok: boolean; message: string };

export type SkuBodyPreviewResult = { preview: string | null };

function str(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.trim() : "";
}

export async function previewProductSkuBodyAction(input: {
  name: string;
  frame_color: string;
  lens_color: string;
  gender: string;
  palette: string;
  style: string;
}): Promise<SkuBodyPreviewResult> {
  const name = input.name.trim();
  const frame_color = input.frame_color.trim();
  const lens_color = input.lens_color.trim();
  const gender = input.gender.trim();
  const palette = input.palette.trim();
  const style = input.style.trim();
  if (!name || !frame_color || !lens_color || !gender || !palette || !style) {
    return { preview: null };
  }
  try {
    const params = new URLSearchParams({
      name,
      frame_color,
      lens_color,
      gender,
      palette,
      style,
    });
    const res = await apiPrototypeFetch(`/products/sku-body-preview?${params.toString()}`);
    if (!res.ok) return { preview: null };
    return (await res.json()) as SkuBodyPreviewResult;
  } catch {
    return { preview: null };
  }
}

export async function createProduct(
  _prev: ProductFormState,
  formData: FormData
): Promise<ProductFormState> {
  if (!hasPrototypeApiUrl()) {
    return {
      ok: false,
      message: "Defina API_PROTOTYPE_URL para cadastrar produtos (a gravação é feita na api-prototype).",
    };
  }

  const admin = await requireAdmin();
  if (admin) return { ok: false, message: admin.message };

  const gate = await gateMutation();
  if (gate) return gate;

  const name = str(formData.get("name"));
  if (!name) return { ok: false, message: "Nome é obrigatório." };

  const registeredDate =
    str(formData.get("registered_date")) || new Date().toISOString().slice(0, 10);
  const frameColor = str(formData.get("frame_color"));
  const lensColor = str(formData.get("lens_color"));
  const style = str(formData.get("style"));
  const palette = str(formData.get("palette"));
  const gender = str(formData.get("gender"));
  const productImageStorageUrl = str(formData.get("product_image_storage_url"));
  const rawFile = formData.get("product_image_file");
  let productImageBase64: string | undefined;
  let productImageFilename = "";
  if (rawFile instanceof Blob && rawFile.size > 0) {
    const maxBytes = 8 * 1024 * 1024;
    if (rawFile.size > maxBytes) {
      return { ok: false, message: "Imagem demasiado grande (máx. 8 MB)." };
    }
    const buf = Buffer.from(await rawFile.arrayBuffer());
    productImageBase64 = buf.toString("base64");
    productImageFilename =
      rawFile instanceof File && rawFile.name?.trim() ? rawFile.name.trim() : "foto.jpg";
  }

  try {
    const imagePayload =
      productImageStorageUrl.trim() !== ""
        ? { product_image_storage_url: productImageStorageUrl }
        : productImageBase64
          ? {
              product_image_base64: productImageBase64,
              product_image_filename: productImageFilename || "foto.jpg",
            }
          : {};

    const res = await apiPrototypeFetch("/products", {
      method: "POST",
      json: {
        name,
        stock: 0,
        registered_date: registeredDate,
        frame_color: frameColor,
        lens_color: lensColor,
        style,
        palette,
        gender,
        unit_cost: 0,
        ...imagePayload,
      },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    const data = (await res.json()) as { product_enter_code?: string };
    const enterCode = String(data.product_enter_code ?? "");
    revalidatePath("/products");
    revalidatePath("/products/new");
    revalidatePath("/inventory");
    return {
      ok: true,
      message: enterCode
        ? `Produto cadastrado com sucesso (código de entrada: ${enterCode}).`
        : "Produto cadastrado com sucesso.",
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao cadastrar produto.",
    };
  }
}

export async function updateProductLotAttributes(
  _prev: LotActionState,
  formData: FormData
): Promise<LotActionState> {
  if (!hasPrototypeApiUrl()) {
    return { ok: false, message: "Defina API_PROTOTYPE_URL." };
  }

  const admin = await requireAdmin();
  if (admin) return { ok: false, message: admin.message };

  const gate = await gateMutation();
  if (gate) return { ok: false, message: gate.message };

  const idRaw = str(formData.get("product_id"));
  const id = Number(idRaw);
  if (!Number.isFinite(id) || id < 1) {
    return { ok: false, message: "Produto inválido." };
  }

  const name = str(formData.get("name"));
  if (!name) {
    return { ok: false, message: "O nome do produto é obrigatório." };
  }
  const registeredDate = str(formData.get("registered_date"));
  if (!registeredDate) {
    return { ok: false, message: "Indique a data de registo." };
  }

  try {
    const res = await apiPrototypeFetch(`/products/${id}/attributes`, {
      method: "PUT",
      json: {
        name,
        registered_date: registeredDate.slice(0, 10),
        frame_color: str(formData.get("frame_color")),
        lens_color: str(formData.get("lens_color")),
        style: str(formData.get("style")),
        palette: str(formData.get("palette")),
        gender: str(formData.get("gender")),
      },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    revalidatePath("/products");
    return {
      ok: true,
      message: "Produto atualizado com sucesso.",
    };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao atualizar atributos.",
    };
  }
}

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

export async function updateProductLotPhoto(
  _prev: LotActionState,
  formData: FormData
): Promise<LotActionState> {
  if (!hasPrototypeApiUrl()) {
    return { ok: false, message: "Defina API_PROTOTYPE_URL." };
  }

  const admin = await requireAdmin();
  if (admin) return { ok: false, message: admin.message };

  const gate = await gateMutation();
  if (gate) return { ok: false, message: gate.message };

  const idRaw = str(formData.get("product_id"));
  const id = Number(idRaw);
  if (!Number.isFinite(id) || id < 1) {
    return { ok: false, message: "Produto inválido." };
  }

  const file = formData.get("photo");
  if (!(file instanceof Blob) || file.size === 0) {
    return { ok: false, message: "Selecione um ficheiro de imagem." };
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return { ok: false, message: "Imagem demasiado grande (máx. 8 MB)." };
  }

  const buf = Buffer.from(await file.arrayBuffer());
  const b64 = buf.toString("base64");
  const name = file instanceof File && file.name ? file.name : "foto.jpg";

  try {
    const res = await apiPrototypeFetch(`/products/${id}/image-bytes`, {
      method: "PATCH",
      json: {
        product_image_base64: b64,
        product_image_filename: name,
      },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    revalidatePath("/products");
    return { ok: true, message: "Imagem do lote atualizada com sucesso." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao gravar foto.",
    };
  }
}

export async function deleteProductSku(
  _prev: LotActionState,
  formData: FormData
): Promise<LotActionState> {
  if (!hasPrototypeApiUrl()) {
    return { ok: false, message: "Defina API_PROTOTYPE_URL." };
  }

  const rbac = await requireAdmin();
  if (rbac) return { ok: false, message: rbac.message };

  const gate = await gateMutation();
  if (gate) return { ok: false, message: gate.message };

  const sku = str(formData.get("sku"));
  if (!sku) return { ok: false, message: "SKU em falta." };

  try {
    const qs = new URLSearchParams({ sku });
    const res = await apiPrototypeFetch(`/products/sku?${qs.toString()}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    revalidatePath("/products");
    revalidatePath("/inventory");
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao eliminar SKU.",
    };
  }

  return { ok: true, message: "SKU excluído com sucesso." };
}

export async function deleteBatch(productEnterCode: string): Promise<ProductFormState> {
  if (!hasPrototypeApiUrl()) {
    return { ok: false, message: "Defina API_PROTOTYPE_URL." };
  }

  const rbac = await requireAdmin();
  if (rbac) return rbac;

  try {
    const res = await apiPrototypeFetch("/pricing/batch/reset", {
      method: "POST",
      json: { product_enter_code: productEnterCode },
    });
    if (!res.ok) {
      return { ok: false, message: await readApiError(res) };
    }
    revalidatePath("/products");
    revalidatePath("/inventory");
    return { ok: true, message: "Lote atualizado (API: reset de precificação/lote)." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Falha ao processar lote.",
    };
  }
}
