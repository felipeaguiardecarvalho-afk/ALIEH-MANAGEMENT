import type { ReactNode } from "react";

export function PageHero({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <section className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
      <div>
        <p className="text-xs uppercase tracking-[0.32em] text-[#d4b36c]">{eyebrow}</p>
        <h1 className="mt-3 font-serif text-4xl font-semibold tracking-tight md:text-5xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </section>
  );
}
