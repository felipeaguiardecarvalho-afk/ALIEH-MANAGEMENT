import type { ReactNode } from "react";

/** Texto da API com `**negrito**` estilo Streamlit → React seguro. */
export function MarkdownHint({ text }: { text: string }): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const m = part.match(/^\*\*([^*]+)\*\*$/);
    if (m) return <strong key={i}>{m[1]}</strong>;
    return <span key={i}>{part}</span>;
  });
}
