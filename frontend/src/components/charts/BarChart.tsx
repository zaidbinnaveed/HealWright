import { useId, useState } from "react";

export interface BarRow {
  key: string;
  label: string;
  value: number | null;
  min?: number | null;
  max?: number | null;
  values?: (number | null)[];
  note?: string;
  emphasis?: boolean;
}

export interface BarSeries {
  name: string;
  color: string; // CSS colour, normally a var(--series-n)
  rows: BarRow[];
}

function ticks(max: number): number[] {
  return [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
}

export function BarChart({
  title,
  description,
  series,
  domainMax,
  format,
  unit,
}: {
  title: string;
  description: string;
  series: BarSeries[];
  domainMax: number;
  format: (v: number) => string;
  unit?: string;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const id = useId();
  const labels = series[0]?.rows ?? [];
  const scale = (v: number) => `${String(Math.max(0, Math.min(1, v / domainMax)) * 100)}%`;
  const multi = series.length > 1;

  return (
    <figure className="rounded-3xl border border-line bg-surface p-5">
      <figcaption>
        <h3 id={`${id}-t`} className="text-sm font-semibold">
          {title}
        </h3>
        <p className="mt-0.5 text-xs text-muted">{description}</p>
      </figcaption>
      {multi ? (
        <ul className="mt-3 flex gap-4 text-xs text-muted" aria-label="Legend">
          {series.map((s) => (
            <li key={s.name} className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
              {s.name}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="relative mt-4" role="list" aria-labelledby={`${id}-t`}>
        <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-40 right-16">
          {ticks(domainMax).map((t) => (
            <div
              key={t}
              className="absolute inset-y-0 border-l border-line"
              style={{ left: scale(t) }}
            />
          ))}
        </div>
        {labels.map((row, i) => (
          <div key={row.key} role="listitem" className="relative flex items-center gap-3 py-1.5">
            <span
              className={`w-37 shrink-0 truncate text-right text-xs ${
                row.emphasis ? "font-semibold text-ink dark:text-white" : "text-muted"
              }`}
              title={row.label}
            >
              {row.label}
            </span>
            <div className="flex flex-1 flex-col gap-0.5">
              {series.map((s) => {
                const r = s.rows[i];
                if (!r) return null;
                const hk = `${s.name}|${r.key}`;
                const range =
                  r.min != null && r.max != null && r.min !== r.max ? ` (range ${format(r.min)} to ${format(r.max)})` : "";
                const text =
                  r.value == null
                    ? `${row.label}${multi ? `, ${s.name}` : ""}: not applicable`
                    : `${row.label}${multi ? `, ${s.name}` : ""}: ${format(r.value)}${unit ?? ""}${range}`;
                return (
                  <div
                    key={hk}
                    tabIndex={0}
                    aria-label={text}
                    onMouseEnter={() => {
                      setHover(hk);
                    }}
                    onMouseLeave={() => {
                      setHover(null);
                    }}
                    onFocus={() => {
                      setHover(hk);
                    }}
                    onBlur={() => {
                      setHover(null);
                    }}
                    className="group relative flex h-5 items-center rounded focus-visible:outline-2"
                  >
                    <div className="relative h-3 flex-1">
                      {r.value != null ? (
                        <div
                          className="absolute inset-y-0 left-0 rounded-r transition-[width] duration-500"
                          style={{ width: scale(r.value), background: s.color, minWidth: r.value > 0 ? 2 : 0 }}
                        />
                      ) : null}
                      {range ? (
                        <div
                          aria-hidden="true"
                          className="absolute top-1/2 h-px -translate-y-1/2 bg-ink"
                          style={{ left: scale(r.min ?? 0), width: `calc(${scale(r.max ?? 0)} - ${scale(r.min ?? 0)})` }}
                        />
                      ) : null}
                    </div>
                    <span className="w-16 shrink-0 pl-2 text-right font-mono text-xs tabular-nums text-muted">
                      {r.value == null ? "n/a" : format(r.value)}
                    </span>
                    {hover === hk ? (
                      <div
                        role="tooltip"
                        className="absolute bottom-full left-1/3 z-10 mb-1 w-max max-w-xs rounded-sm bg-ink px-3 py-2 text-xs text-bg shadow-lg"
                      >
                        <p className="font-semibold">
                          {row.label}
                          {multi ? ` · ${s.name}` : ""}
                        </p>
                        <p className="mt-0.5 tabular-nums">
                          {r.value == null ? "not applicable" : `mean ${format(r.value)}${unit ?? ""}`}
                          {range}
                        </p>
                        {r.values && r.values.length > 1 ? (
                          <p className="mt-0.5 opacity-75">
                            per run: {r.values.map((v) => (v == null ? "n/a" : format(v))).join(", ")}
                          </p>
                        ) : null}
                        {r.note ? <p className="mt-0.5 opacity-75">{r.note}</p> : null}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </figure>
  );
}
