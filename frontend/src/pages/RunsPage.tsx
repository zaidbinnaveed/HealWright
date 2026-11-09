import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, request } from "../api/client";
import type { HealStatus, Page, RunSummary } from "../api/types";
import { EmptyState, ErrorBanner } from "../components/States";
import { Button, ButtonLink } from "../components/ui/Button";
import { Card, SectionHeader } from "../components/ui/Cards";
import { SkeletonRows } from "../components/ui/Feedback";
import { SearchInput } from "../components/ui/Inputs";
import { Pagination, SegmentedTabs } from "../components/ui/Navigation";
import { useTitle } from "../lib/useTitle";

const STATUS: { key: HealStatus; label: string; dot: string }[] = [
  { key: "healed", label: "Healed", dot: "#10b981" },
  { key: "suggested", label: "Suggested", dot: "#38bdf8" },
  { key: "needs_human", label: "Needs human", dot: "#f59e0b" },
  { key: "regression_suspected", label: "Regression", dot: "#ef4444" },
];

type Filter = "all" | HealStatus;
type SortKey = "started_at" | "event_count";
const PAGE = 20;
const ROWS = 10;

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function SortHeader({
  label,
  k,
  sort,
  onSort,
}: {
  label: string;
  k: SortKey;
  sort: { key: SortKey; desc: boolean };
  onSort: (k: SortKey) => void;
}) {
  const active = sort.key === k;
  return (
    <th scope="col" aria-sort={active ? (sort.desc ? "descending" : "ascending") : "none"} className="px-4 py-3 font-medium">
      <button type="button" onClick={() => { onSort(k); }} className="inline-flex items-center gap-1 hover:text-ink">
        {label}
        <span aria-hidden="true" className={active ? "text-ink" : "opacity-30"}>{active && !sort.desc ? "↑" : "↓"}</span>
      </button>
    </th>
  );
}

export function RunsPage() {
  useTitle("Runs", "Every pytest session that needed a heal.");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "started_at", desc: true });
  const [page, setPage] = useState(1);
  const navigate = useNavigate();

  const load = useCallback((from: string | null) => {
    setLoading(true);
    setError(null);
    const qs = new URLSearchParams({ limit: String(PAGE) });
    if (from) qs.set("cursor", from);
    request<Page<RunSummary>>(`/runs?${qs.toString()}`)
      .then((p) => {
        setRuns((prev) => (from ? [...prev, ...p.items] : p.items));
        setCursor(p.next_cursor);
        setDone(p.next_cursor === null);
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e), null));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load(null);
  }, [load]);

  const totals = useMemo(() => {
    const t = Object.fromEntries(STATUS.map((s) => [s.key, 0])) as Record<HealStatus, number>;
    for (const r of runs) for (const s of STATUS) t[s.key] += r.status_counts[s.key];
    return t;
  }, [runs]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = runs.filter((r) => {
      if (filter !== "all" && r.status_counts[filter] === 0) return false;
      if (!q) return true;
      return r.run_id.toLowerCase().includes(q) || r.tests.some((t) => t.toLowerCase().includes(q));
    });
    const dir = sort.desc ? -1 : 1;
    return [...rows].sort((a, b) =>
      sort.key === "started_at" ? dir * a.started_at.localeCompare(b.started_at) : dir * (a.event_count - b.event_count),
    );
  }, [runs, filter, query, sort]);

  const pages = Math.max(1, Math.ceil(visible.length / ROWS));
  const current = Math.min(page, pages);
  const shown = visible.slice((current - 1) * ROWS, current * ROWS);
  const onSort = (k: SortKey) => {
    setSort((s) => ({ key: k, desc: s.key === k ? !s.desc : true }));
  };

  return (
    <div className="space-y-8">
      <SectionHeader as="h1" eyebrow="Workspace" title="Runs">
        Every pytest session that needed a heal, newest first.
      </SectionHeader>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {STATUS.map((s) => (
          <Card key={s.key} className="p-4!">
            <dt className="flex items-center gap-2 text-xs text-muted">
              <span aria-hidden="true" className="uv-dot" style={{ ["--background-tooltip-container" as string]: s.dot }} />
              {s.label}
            </dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{totals[s.key]}</dd>
          </Card>
        ))}
      </dl>

      <Card className="p-0!">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <SearchInput
            value={query}
            onChange={(v) => { setQuery(v); setPage(1); }}
            label="Search runs"
            placeholder="Search by test name or run id"
          />
          <SegmentedTabs<Filter>
            label="Filter by status"
            value={filter}
            onChange={(f) => { setFilter(f); setPage(1); }}
            options={[{ value: "all", label: "All" }, ...STATUS.map((s) => ({ value: s.key, label: s.label, count: totals[s.key] }))]}
          />
        </div>

        {error ? (
          <div className="p-4"><ErrorBanner error={error} onRetry={() => { load(null); }} /></div>
        ) : loading && runs.length === 0 ? (
          <SkeletonRows rows={4} className="p-2" />
        ) : runs.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No runs yet" action={<ButtonLink to="/demo">Try the live demo</ButtonLink>}>
              Runs appear here when a test step breaks and HealWright tries to heal it.
            </EmptyState>
          </div>
        ) : visible.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No runs match" action={<Button variant="secondary" onClick={() => { setFilter("all"); setQuery(""); }}>Clear filters</Button>}>
              Change the filter or the search text.
            </EmptyState>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-line">
                  <th scope="col" className="px-4 py-3 font-medium">Run</th>
                  <SortHeader label="Started" k="started_at" sort={sort} onSort={onSort} />
                  <SortHeader label="Events" k="event_count" sort={sort} onSort={onSort} />
                  <th scope="col" className="px-4 py-3 font-medium">Outcomes</th>
                  <th scope="col" className="px-4 py-3 font-medium">Tier 1 / 2</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => { void navigate(`/runs/${r.run_id}`); }}
                    className="cursor-pointer border-b border-line transition-colors last:border-0 hover:bg-chip"
                  >
                    <td className="max-w-md px-4 py-3">
                      <Link to={`/runs/${r.run_id}`} onClick={(e) => { e.stopPropagation(); }} className="font-mono text-xs font-medium hover:underline">
                        {r.run_id}
                      </Link>
                      <p className="mt-0.5 truncate font-mono text-xs text-dim">{r.tests.join(", ")}</p>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted">{when(r.started_at)}</td>
                    <td className="px-4 py-3 tabular-nums">{r.event_count}</td>
                    <td className="px-4 py-3">
                      <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
                        {STATUS.map((s) =>
                          r.status_counts[s.key] > 0 ? (
                            <span key={s.key} className="inline-flex items-center gap-1.5">
                              <span aria-hidden="true" className="uv-dot" style={{ ["--background-tooltip-container" as string]: s.dot }} />
                              <span className="font-semibold tabular-nums">{r.status_counts[s.key]}</span>
                              <span className="text-muted">{s.label.toLowerCase()}</span>
                            </span>
                          ) : null,
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted tabular-nums">
                      {r.tier_counts["1"]} / {r.tier_counts["2"]}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {visible.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line p-3">
            <p className="text-xs text-muted">
              {visible.length} run{visible.length === 1 ? "" : "s"} loaded{done ? "" : " (more on the server)"}
            </p>
            <Pagination page={current} pages={pages} onPage={setPage} />
            {!done ? (
              <Button variant="secondary" disabled={loading} onClick={() => { load(cursor); }}>
                {loading ? "Loading…" : "Load more"}
              </Button>
            ) : <span />}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
