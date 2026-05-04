"use client";

import type { ComponentProps } from "react";

type Props = Omit<ComponentProps<"form">, "onSubmit"> & {
  confirmMessage: string;
};

export function ConfirmDeleteForm({ confirmMessage, children, ...rest }: Props) {
  return (
    <form
      {...rest}
      onSubmit={(e) => {
        if (!window.confirm(confirmMessage)) e.preventDefault();
      }}
    >
      {children}
    </form>
  );
}
