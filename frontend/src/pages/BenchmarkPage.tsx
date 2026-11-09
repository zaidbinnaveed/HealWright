import { useMemo, useState } from "react";
import { useResource } from "../api/client";
import type { CombinedBenchmark, CombinedScenario, CombinedSystem, Outcome, Stat } from "../api/types";
import { BarChart, type BarRow } from "../components/charts/BarChart";
import { EmptyState, ErrorBanner, SkeletonCard } from "../components/States";
import { SectionHeader, StatCard } from "../components/ui/Cards";
import { Checkbox } from "../components/ui/Feedback";
import { SegmentedTabs } from "../components/ui/Navigation";
import { useTitle } from "../lib/useTitle";

const SYSTEMS: { key: string; label: string; group: "baseline" | "ours" | "ablation"; blurb: string }[] = [
  { key: "native", label: "Native Playwright", group: "baseline", blurb: "plugin off" },
  { key: "greedy", label: "Greedy matcher", group: "baseline", blurb: "no gate, no verifier, no Tier 2" },
  { key: "rawhtml", label: "Raw-HTML LLM", group: "baseline", blurb: "page HTML to one CSS selector, used as-is" },
  { key: "healwright", label: "HealWright", group: "ours", blurb: "Tier 1 + Tier 2 + verifier" },
  { key: "tier1_only", label: "Tier 1 only", group: "ablation", blurb: "Tier 2 off" },
  { key: "healwright_noverify", label: "No verifier", group: "ablation", blurb: "verifier off" },
];

const CLASS_LABEL: Record<string, string> = {
  id_rename: "ID rename",
  css_refactor: "CSS refactor",
  copy_drift: "Copy drift",
  tag_to_aria: "Tag to ARIA",
  layout_move: "Layout move",
  i18n: "i18n",
  distractor_trap: "Distractor trap",
  regression_trap: "Regression trap",
};

const pct = (v: number) => `${(v * 100).toFixed(1).replace(/\.0$/, "")}%`;
const num = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2));
const ms = (v: number) => Math.round(v).toLocaleString();

function label(key: string): string {
  return SYSTEMS.find((s) => s.key === key)?.label ?? key;
}

function ordered(systems: CombinedSystem[]): CombinedSystem[] {
  const rank = (k: string) => {
    const i = SYSTEMS.findIndex((s) => s.key === k);
    return i === -1 ? SYSTEMS.length : i;
  };
  return [...systems].sort((a, b) => rank(a.system) - rank(b.system));
}

function rows(systems: CombinedSystem[], metric: string, note?: (s: CombinedSystem) => string | undefined): BarRow[] {
  return systems.map((s) => {
    const st: Stat | undefined = s.summary[metric];
    return {
      key: s.system,
      label: label(s.system),
      value: st?.mean ?? null,
      min: st?.min,
      max: st?.max,
      values: st?.values,
      note: note?.(s),
      emphasis: s.system === "healwright",
    };
  });
}

function maxOf(systems: CombinedSystem[], metric: string): number {
  return Math.max(1, ...systems.map((s) => s.summary[metric]?.max ?? 0));
}

function fmtStat(st: Stat | undefined, f: (v: number) => string): string {
  if (!st || st.mean == null) return "n/a";
  if (st.min != null && st.max != null && st.min !== st.max) return `${f(st.mean)} (${f(st.min)} to ${f(st.max)})`;
  return f(st.mean);
}

/** Mean for the big number; the min-to-max range goes in the caption. */
function meanOf(st: Stat | undefined, f: (v: number) => string): string {
  return st?.mean == null ? "n/a" : f(st.mean);
}
function rangeOf(st: Stat | undefined, f: (v: number) => string): string {
  return st && st.min != null && st.max != null && st.min !== st.max ? `range ${f(st.min)} to ${f(st.max)}` : "same in every run";
}

const OUTCOME: Record<Outcome, { short: string; text: string; cls: string }> = {
  true_heal: { short: "✓", text: "true heal", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200" },
  false_heal: { short: "✗", text: "false heal", cls: "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200" },
  red: { short: "R", text: "stayed red", cls: "bg-chip-hover text-ink" },
  error: { short: "E", text: "harness error (excluded)", cls: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200" },
};

function ClassBreakdown({ systems }: { systems: CombinedSystem[] }) {
  const [sel, setSel] = useState("healwright");
  const sys = systems.find((s) => s.system === sel) ?? systems[0];
  if (!sys) return null;
  const classes = Object.keys(CLASS_LABEL).filter((c) => c in sys.by_class);
  const segs = [
    { k: "true_heal" as const, name: "True heal", color: "var(--status-good)" },
    { k: "false_heal" as const, name: "False heal", color: "var(--status-critical)" },
    { k: "red" as const, name: "Stayed red", color: "var(--status-neutral)" },
  ];
  return (
    <section aria-labelledby="by-class" className="rounded-3xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="by-class" className="text-sm font-semibold">
            Outcomes by mutation class
          </h2>
          <p className="mt-0.5 text-xs text-muted">
            Scenario runs summed over all {sys.runs} run(s); harness errors excluded. On traps, “stayed red” is the
            correct outcome.
          </p>
        </div>
        <SegmentedTabs
          label="System"
          value={sys.system}
          onChange={setSel}
          options={systems.map((s) => ({ value: s.system, label: label(s.system) }))}
        />
      </div>
      <ul className="mt-3 flex gap-4 text-xs text-muted" aria-label="Legend">
        {segs.map((s) => (
          <li key={s.k} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
            {s.name}
          </li>
        ))}
      </ul>
      <table className="mt-4 w-full text-xs">
        <thead className="sr-only">
          <tr>
            <th>Class</th>
            <th>Distribution</th>
            {segs.map((s) => (
              <th key={s.k}>{s.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {classes.map((c) => {
            const n = sys.by_class[c];
            if (!n) return null;
            return (
              <tr key={c}>
                <th scope="row" className="w-32 py-1.5 pr-3 text-left font-normal text-muted">
                  {CLASS_LABEL[c]}
                </th>
                <td className="py-1.5">
                  <div
                    className="flex h-3 overflow-hidden rounded"
                    style={{ gap: 2, background: "var(--chart-gap)" }}
                    aria-hidden="true"
                  >
                    {segs.map((s) =>
                      n[s.k] > 0 ? (
                        <div
                          key={s.k}
                          title={`${s.name}: ${String(n[s.k])} of ${String(n.scored)}`}
                          style={{ flexGrow: n[s.k], background: s.color }}
                        />
                      ) : null,
                    )}
                  </div>
                </td>
                {segs.map((s) => (
                  <td key={s.k} className="w-14 py-1.5 text-right font-mono tabular-nums text-muted">
                    <span className="sr-only">{s.name} </span>
                    {n[s.k]}/{n.scored}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function ScenarioTable({ scenarios, systems }: { scenarios: CombinedScenario[]; systems: CombinedSystem[] }) {
  const [klass, setKlass] = useState("all");
  const [onlyDiff, setOnlyDiff] = useState(false);
  const shown = scenarios.filter((s) => {
    if (klass !== "all" && s.class !== klass) return false;
    if (!onlyDiff) return true;
    const all = systems.filter((x) => x.system !== "native").flatMap((x) => s.outcomes[x.system] ?? []);
    return new Set(all).size > 1;
  });
  return (
    <section aria-labelledby="scenarios" className="rounded-3xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="scenarios" className="text-sm font-semibold">
            Scenario table (eval split, {scenarios.length} scenarios)
          </h2>
          <p className="mt-0.5 text-xs text-muted">
            One mark per run: {Object.values(OUTCOME).map((o) => `${o.short} ${o.text}`).join(" · ")}
          </p>
        </div>
        <div className="flex flex-col items-end gap-3 text-xs text-muted">
          <SegmentedTabs
            label="Mutation class"
            value={klass}
            onChange={setKlass}
            options={[{ value: "all", label: "All" }, ...Object.entries(CLASS_LABEL).map(([k, v]) => ({ value: k, label: v }))]}
          />
          <Checkbox checked={onlyDiff} onChange={setOnlyDiff}>
            Only scenarios where systems disagree
          </Checkbox>
        </div>
      </div>
      <div className="mt-4 max-h-[32rem] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-line text-left text-dim">
              <th scope="col" className="py-2 pr-3 font-medium">
                Scenario
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Class
              </th>
              {systems.map((s) => (
                <th key={s.system} scope="col" className="py-2 pr-3 font-medium">
                  {label(s.system)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((sc) => (
              <tr key={sc.id} className="border-b border-line">
                <th scope="row" className="py-1.5 pr-3 text-left font-mono font-normal">
                  {sc.id}
                </th>
                <td className="py-1.5 pr-3 text-muted">{CLASS_LABEL[sc.class] ?? sc.class}</td>
                {systems.map((s) => (
                  <td key={s.system} className="py-1.5 pr-3">
                    <span className="flex gap-1">
                      {(sc.outcomes[s.system] ?? []).map((o, i) => (
                        <span
                          key={i}
                          title={`run ${String(i + 1)}: ${OUTCOME[o].text}`}
                          className={`inline-flex h-5 w-5 items-center justify-center rounded font-semibold ${OUTCOME[o].cls}`}
                        >
                          <span aria-hidden="true">{OUTCOME[o].short}</span>
                          <span className="sr-only">{`run ${String(i + 1)}: ${OUTCOME[o].text}`}</span>
                        </span>
                      ))}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 ? <p className="py-6 text-center text-sm text-dim">No scenarios match.</p> : null}
      </div>
    </section>
  );
}

function SummaryTable({ systems }: { systems: CombinedSystem[] }) {
  const cols: { k: string; h: string; f: (v: number) => string }[] = [
    { k: "true_heal_rate", h: "True heal rate", f: pct },
    { k: "false_heals_on_traps", h: "False heals on traps", f: num },
    { k: "precision_of_accepted_heals", h: "Precision", f: pct },
    { k: "tier1_share_of_heals", h: "Tier-1 share", f: pct },
    { k: "latency_ms.all_heals.p50", h: "Latency p50 (ms)", f: ms },
    { k: "latency_ms.all_heals.p95", h: "Latency p95 (ms)", f: ms },
    { k: "provider_failures", h: "Provider failures", f: num },
    { k: "errors", h: "Harness errors (excluded)", f: num },
  ];
  return (
    <section aria-labelledby="summary" className="rounded-3xl border border-line bg-surface p-5">
      <h2 id="summary" className="text-sm font-semibold">
        All metrics (table view)
      </h2>
      <p className="mt-0.5 text-xs text-muted">Mean over runs, with min to max where it varies.</p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line text-left text-dim">
              <th scope="col" className="py-2 pr-3 font-medium">
                System
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Runs
              </th>
              {cols.map((c) => (
                <th key={c.k} scope="col" className="py-2 pr-3 font-medium">
                  {c.h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {systems.map((s) => (
              <tr key={s.system} className="border-b border-line">
                <th scope="row" className={`py-2 pr-3 text-left ${s.system === "healwright" ? "font-semibold" : "font-normal"}`}>
                  {label(s.system)}
                </th>
                <td className="py-2 pr-3 tabular-nums">{s.runs}</td>
                {cols.map((c) => (
                  <td key={c.k} className="py-2 pr-3 font-mono tabular-nums">
                    {fmtStat(s.summary[c.k], c.f)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function BenchmarkPage() {
  useTitle("Benchmark", "HealWright against greedy healing, a raw-HTML LLM and its own ablations.");
  const { data, error, loading, reload } = useResource<CombinedBenchmark>("/benchmarks/combined");
  const systems = useMemo(() => ordered(data?.systems ?? []), [data]);
  const hw = systems.find((s) => s.system === "healwright");
  const models = systems.filter((s) => s.system !== "native");
  const rawNote = (s: CombinedSystem) =>
    s.system === "rawhtml" ? "One LLM call per broken step: no Tier 1, so the share is 0 by design." : undefined;

  return (
    <div className="space-y-6">
      <SectionHeader as="h1" eyebrow="Chaos Benchmark" title="Benchmark">
        Eval split (frozen; 40 healable scenarios and 10 traps). Systems with a model run 3 times (1 record + 2 live,
        Groq). Harness errors are excluded from every denominator and shown separately.
      </SectionHeader>

      {error ? <ErrorBanner error={error} onRetry={reload} /> : null}
      {loading && !data ? (
        <div className="grid gap-4 md:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : null}
      {data && systems.length === 0 ? (
        <EmptyState title="No combined benchmark yet">
          Run the eval benchmark, then <code className="font-mono">python -m benchmark.combine</code>.
        </EmptyState>
      ) : null}

      {hw ? (
        <div className="grid gap-4 md:grid-cols-3">
          <StatCard
            label="HealWright true heal rate"
            value={meanOf(hw.summary.true_heal_rate, pct)}
            caption={`mean of ${String(hw.runs)} runs · ${rangeOf(hw.summary.true_heal_rate, pct)}`}
          />
          <StatCard
            label="False heals on traps"
            value={meanOf(hw.summary.false_heals_on_traps, num)}
            caption={`per run · ${rangeOf(hw.summary.false_heals_on_traps, num)}`}
          />
          <StatCard
            label="Precision of accepted heals"
            value={meanOf(hw.summary.precision_of_accepted_heals, pct)}
            caption={`accepted heals on the true target · ${rangeOf(hw.summary.precision_of_accepted_heals, pct)}`}
          />
        </div>
      ) : null}

      {systems.length > 0 ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <BarChart
              title="True heal rate"
              description="Healable scenarios healed to the right element (higher is better). Whisker: min to max over runs."
              series={[{ name: "True heal rate", color: "var(--series-1)", rows: rows(systems, "true_heal_rate") }]}
              domainMax={1}
              format={pct}
            />
            <BarChart
              title="False heals on traps"
              description="Trap scenarios where the system made the test pass the wrong way (lower is better), per run."
              series={[
                { name: "False heals", color: "var(--series-1)", rows: rows(systems, "false_heals_on_traps") },
              ]}
              domainMax={maxOf(systems, "false_heals_on_traps")}
              format={num}
            />
            <BarChart
              title="Tier-1 share of heals"
              description="Heals decided by the deterministic matcher, without a model call."
              series={[
                { name: "Tier-1 share", color: "var(--series-1)", rows: rows(models, "tier1_share_of_heals", rawNote) },
              ]}
              domainMax={1}
              format={pct}
            />
            <BarChart
              title="Heal latency, all heals"
              description="Milliseconds from failure to decision, p50 and p95 (mean over runs)."
              series={[
                { name: "p50", color: "var(--series-1)", rows: rows(models, "latency_ms.all_heals.p50") },
                { name: "p95", color: "var(--series-2)", rows: rows(models, "latency_ms.all_heals.p95") },
              ]}
              domainMax={Math.max(...models.map((s) => s.summary["latency_ms.all_heals.p95"]?.mean ?? 0), 1)}
              format={ms}
              unit=" ms"
            />
          </div>
          <section aria-labelledby="ablations" className="rounded-3xl border border-line bg-surface p-5">
            <h2 id="ablations" className="text-sm font-semibold">
              Ablations: what each part contributes
            </h2>
            <dl className="mt-3 grid gap-3 text-sm md:grid-cols-3">
              {(["healwright", "tier1_only", "healwright_noverify"] as const).map((k) => {
                const s = systems.find((x) => x.system === k);
                if (!s) return null;
                return (
                  <div key={k} className="rounded-lg bg-chip p-3">
                    <dt className="font-medium">
                      {label(k)} <span className="text-xs font-normal text-dim">({SYSTEMS.find((x) => x.key === k)?.blurb})</span>
                    </dt>
                    <dd className="mt-1 font-mono text-xs tabular-nums text-muted">
                      true heal rate {fmtStat(s.summary.true_heal_rate, pct)} · false heals{" "}
                      {fmtStat(s.summary.false_heals_on_traps, num)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </section>
          <ClassBreakdown systems={systems} />
          <SummaryTable systems={systems} />
          <ScenarioTable scenarios={data?.scenarios ?? []} systems={systems} />
        </>
      ) : null}
    </div>
  );
}
