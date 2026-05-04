"use client";

import { useCallback, useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";

import { mintProductImageSignedUpload } from "@/lib/actions/product-image-upload";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ActionSuccessToast } from "@/components/action-success-toast";

const MAX_BYTES = 8 * 1024 * 1024;

function supabaseBrowser() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url || !anon) return null;
  return createClient(url, anon);
}

export function ProductImageUpload({ resetNonce = 0 }: { resetNonce?: number }) {
  const [publicUrl, setPublicUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [uploadOk, setUploadOk] = useState(false);

  const clear = useCallback(() => {
    setPublicUrl("");
    setMessage(null);
    setUploadOk(false);
  }, []);

  useEffect(() => {
    clear();
  }, [resetNonce, clear]);

  const onFile = async (file: File | undefined) => {
    setMessage(null);
    setUploadOk(false);
    if (!file) {
      clear();
      return;
    }
    if (!file.type.startsWith("image/")) {
      setMessage("Escolha um ficheiro de imagem.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setMessage("Imagem demasiado grande (máx. 8 MB).");
      return;
    }

    const sb = supabaseBrowser();
    if (!sb) {
      setMessage("Configure NEXT_PUBLIC_SUPABASE_URL e NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      return;
    }

    setBusy(true);
    try {
      const minted = await mintProductImageSignedUpload(file.name, file.type || "image/jpeg");
      if (!minted.ok) {
        setMessage(minted.message);
        return;
      }

      const { error: upErr } = await sb.storage
        .from(minted.bucket)
        .uploadToSignedUrl(minted.path, minted.token, file, {
          contentType: file.type || "image/jpeg",
        });
      if (upErr) {
        setMessage(upErr.message || "Falha no upload para o Storage.");
        return;
      }

      const { data: pub } = sb.storage.from(minted.bucket).getPublicUrl(minted.path);
      const url = pub?.publicUrl?.trim() ?? "";
      if (!url) {
        setMessage("Upload concluído mas não foi possível obter URL pública (bucket público?).");
        return;
      }
      setPublicUrl(url);
      setUploadOk(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-2xl border border-dashed border-border/80 bg-muted/20 p-4">
      <ActionSuccessToast
        message="Imagem enviada para o Storage com sucesso."
        visible={uploadOk}
        onDismiss={() => setUploadOk(false)}
        durationMs={4000}
      />
      <input type="hidden" name="product_image_storage_url" value={publicUrl} readOnly />

      <div className="space-y-2">
        <Label htmlFor="product_image_storage_pick">Imagem do produto (Supabase)</Label>
        <Input
          id="product_image_storage_pick"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          disabled={busy}
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
        <p className="text-xs text-muted-foreground">
          O ficheiro envia-se diretamente para o Supabase Storage (URL assinada pela API de protótipo; sem bytes
          através do servidor Next).
        </p>
      </div>

      {message ? <p className="text-sm text-destructive">{message}</p> : null}

      {busy ? <p className="text-sm text-muted-foreground">A enviar…</p> : null}

      {publicUrl ? (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Pré-visualização (URL guardada no cadastro)</p>
          <div className="flex items-start gap-3">
            <img
              src={publicUrl}
              alt="Pré-visualização do produto"
              className="h-24 w-24 rounded-lg border border-border/60 object-cover"
            />
            <Button type="button" variant="outline" size="sm" onClick={clear}>
              Remover imagem
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
