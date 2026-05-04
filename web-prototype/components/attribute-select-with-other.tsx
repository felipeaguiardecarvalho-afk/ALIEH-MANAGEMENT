"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

/** Sentinel for the "Other" row — never stored in the database. */
export const ATTRIBUTE_OTHER_SELECT_VALUE = "__attribute_other__";

type Props = {
  name: string;
  label: string;
  /** Preset values (from domain and/or API); duplicates trimmed. */
  presetOptions: string[];
  /** Current stored value (may be custom, not in presets). */
  initialValue?: string | null;
  /** First option label for empty selection. */
  emptyLabel: string;
  /** Chamado quando o valor gravado no formulário (preset ou &quot;Outro&quot;) muda. */
  onResolvedChange?: (value: string) => void;
  /** Quando verdadeiro, não permite alterar (ex.: lote bloqueado por custo/vendas). */
  disabled?: boolean;
};

export function AttributeSelectWithOther({
  name,
  label,
  presetOptions,
  initialValue,
  emptyLabel,
  onResolvedChange,
  disabled = false,
}: Props) {
  const presets = useMemo(() => {
    const set = new Set<string>();
    for (const raw of presetOptions) {
      const s = (raw ?? "").trim();
      if (s && s !== ATTRIBUTE_OTHER_SELECT_VALUE) set.add(s);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b, "pt"));
  }, [presetOptions]);

  const normalizedInitial = (initialValue ?? "").trim();
  const initialIsCustom = normalizedInitial !== "" && !presets.includes(normalizedInitial);

  const [otherMode, setOtherMode] = useState(initialIsCustom);
  const [otherText, setOtherText] = useState(initialIsCustom ? normalizedInitial : "");
  const [presetValue, setPresetValue] = useState(initialIsCustom ? "" : normalizedInitial);

  const resolved = otherMode ? otherText.trim() : presetValue;

  const onResolvedRef = useRef(onResolvedChange);
  onResolvedRef.current = onResolvedChange;

  useEffect(() => {
    onResolvedRef.current?.(resolved);
  }, [resolved]);

  const controlId = `attr-${name}`;

  return (
    <div className="space-y-2">
      <Label htmlFor={controlId}>{label}</Label>
      <input
        type="hidden"
        name={name}
        value={resolved}
        onChange={() => {
          /* value driven by select / text above */
        }}
        aria-hidden
      />

      {otherMode ? (
        <div className="space-y-2">
          <Input
            id={controlId}
            value={otherText}
            onChange={(e) => setOtherText(e.target.value)}
            placeholder="Descreva o valor (gravado tal como escrito)"
            autoComplete="off"
            disabled={disabled}
          />
          <button
            type="button"
            disabled={disabled}
            className="text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
            onClick={() => {
              setOtherMode(false);
              setOtherText("");
              setPresetValue("");
            }}
          >
            Usar lista predefinida
          </button>
        </div>
      ) : (
        <Select
          id={controlId}
          value={presetValue}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value;
            if (v === ATTRIBUTE_OTHER_SELECT_VALUE) {
              setOtherMode(true);
              setOtherText("");
            } else {
              setPresetValue(v);
            }
          }}
        >
          <option value="">{emptyLabel}</option>
          {presets.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
          <option value={ATTRIBUTE_OTHER_SELECT_VALUE}>Outro…</option>
        </Select>
      )}
    </div>
  );
}
