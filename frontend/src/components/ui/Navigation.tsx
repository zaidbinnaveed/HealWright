import { motion, useReducedMotion } from "framer-motion";
import { useId, type ReactNode } from "react";

export function DotTabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex items-center gap-2 text-sm">
      {tabs.map((t, i) => (
        <span key={t.value} className="flex items-center gap-2">
          {i > 0 ? (
            <span aria-hidden="true" className="text-[11px] text-dim">
              ·
            </span>
          ) : null}
          <button
            type="button"
            role="tab"
            aria-selected={t.value === value}
            onClick={() => {
              onChange(t.value);
            }}
            className={`py-0.5 transition-colors ${t.value === value ? "text-ink" : "text-dim hover:text-muted"}`}
          >
            {t.label}
          </button>
        </span>
      ))}
    </div>
  );
}

export function SegmentedTabs<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const group = useId();
  const reduce = useReducedMotion();
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-line bg-chip p-1">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => {
              onChange(o.value);
            }}
            className={`relative rounded-full px-3 py-1 text-xs font-medium transition-colors ${active ? "text-bg" : "text-muted hover:text-ink"}`}
          >
            {active ? (
              <motion.span
                layoutId={`seg-${group}`}
                transition={reduce ? { duration: 0 } : { type: "spring", bounce: 0.2, duration: 0.4 }}
                className="absolute inset-0 rounded-full bg-ink"
              />
            ) : null}
            <span className="relative flex items-center gap-1.5">
              {o.label}
              {o.count !== undefined ? <span className="tabular-nums opacity-70">{o.count}</span> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  onPage,
}: {
  page: number;
  pages: number;
  onPage: (p: number) => void;
}) {
  if (pages <= 1) return null;
  const nums = Array.from({ length: pages }, (_, i) => i + 1).filter(
    (n) => n === 1 || n === pages || Math.abs(n - page) <= 1,
  );
  const ghost = "inline-flex h-8 min-w-8 items-center justify-center rounded-lg px-2 text-sm transition-colors hover:bg-chip-hover disabled:pointer-events-none disabled:opacity-40";
  return (
    <nav aria-label="Pagination" className="flex items-center justify-center gap-1">
      <button type="button" className={ghost} disabled={page <= 1} onClick={() => { onPage(page - 1); }}>
        ‹ Previous
      </button>
      {nums.map((n, i) => (
        <span key={n} className="flex items-center gap-1">
          {i > 0 && n - (nums[i - 1] ?? n) > 1 ? <span className="px-1 text-dim">…</span> : null}
          <button
            type="button"
            aria-current={n === page ? "page" : undefined}
            className={`${ghost} ${n === page ? "border border-line bg-surface font-semibold" : "text-muted"}`}
            onClick={() => { onPage(n); }}
          >
            {n}
          </button>
        </span>
      ))}
      <button type="button" className={ghost} disabled={page >= pages} onClick={() => { onPage(page + 1); }}>
        Next ›
      </button>
    </nav>
  );
}

export function Stepper({
  steps,
  current,
  failed = false,
}: {
  steps: { label: string; detail?: string }[];
  current: number; // index of the active step; steps.length = all done
  failed?: boolean;
}) {
  const reduce = useReducedMotion();
  return (
    <ol className="grid gap-4" style={{ gridTemplateColumns: `repeat(${String(steps.length)}, minmax(0, 1fr))` }}>
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current && !failed;
        const bad = i === current && failed;
        return (
          <li key={s.label} className="relative">
            {i < steps.length - 1 ? (
              <span aria-hidden="true" className="absolute top-3 left-[calc(50%+16px)] h-px w-[calc(100%-32px+1rem)] bg-line">
                <motion.span
                  className="absolute inset-y-0 left-0 bg-ink"
                  initial={false}
                  animate={{ width: done ? "100%" : "0%" }}
                  transition={reduce ? { duration: 0 } : { duration: 0.4 }}
                />
              </span>
            ) : null}
            <div className="flex flex-col items-center text-center">
              <span
                className={`relative flex size-6 items-center justify-center rounded-full text-xs font-semibold ${
                  done ? "bg-ink text-bg" : active ? "bg-ink text-bg ring-4 ring-accent/30" : bad ? "bg-red-600 text-white" : "bg-chip-hover text-muted"
                }`}
              >
                {done ? "✓" : bad ? "!" : i + 1}
                {active && !reduce ? (
                  <motion.span
                    aria-hidden="true"
                    className="absolute inset-0 rounded-full ring-2 ring-accent"
                    animate={{ opacity: [0.8, 0, 0.8], scale: [1, 1.5, 1] }}
                    transition={{ repeat: Infinity, duration: 1.6 }}
                  />
                ) : null}
              </span>
              <p className={`mt-2 text-xs font-semibold ${done || active ? "text-ink" : "text-muted"}`}>
                {s.label}
                <span className="sr-only">{done ? " (done)" : active ? " (in progress)" : bad ? " (failed)" : " (waiting)"}</span>
              </p>
              {s.detail ? <p className="mt-0.5 text-[11px] text-dim">{s.detail}</p> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function Timeline({
  items,
}: {
  items: { key: string; title: string; meta?: string; tone?: "ok" | "bad" | "skip" | "neutral"; icon?: ReactNode; children?: ReactNode }[];
}) {
  const ring: Record<string, string> = {
    ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-500",
    bad: "border-red-500/40 bg-red-500/10 text-red-500",
    skip: "border-line bg-chip text-dim",
    neutral: "border-line bg-chip text-muted",
  };
  return (
    <ol className="relative">
      {items.map((it, i) => (
        <li key={it.key} className="relative flex gap-4 pb-6 last:pb-0">
          {i < items.length - 1 ? <span aria-hidden="true" className="absolute top-8 bottom-0 left-[15px] w-px bg-line" /> : null}
          <span aria-hidden="true" className={`z-10 flex size-8 shrink-0 items-center justify-center rounded-full border ${ring[it.tone ?? "neutral"] ?? ""}`}>
            {it.icon ?? <span className="size-1.5 rounded-full bg-current" />}
          </span>
          <div className="min-w-0 flex-1 pt-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4">
              <p className="text-sm font-semibold">{it.title}</p>
              {it.meta ? <p className="font-mono text-xs text-dim tabular-nums">{it.meta}</p> : null}
            </div>
            {it.children ? <div className="mt-1 text-sm text-muted">{it.children}</div> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
