import { ButtonLink } from "../components/ui/Button";
import { motion, useReducedMotion } from "framer-motion";
import { Link, useParams } from "react-router";
import { useResource } from "../api/client";
import type { RunDetail } from "../api/types";
import { EmptyState, ErrorBanner, Skeleton, SkeletonCard } from "../components/States";
import { StatusBadge, TriageBadge } from "../components/StatusBadge";
import { useTitle } from "../lib/useTitle";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  useTitle(`Run ${runId.slice(-8)}`, "Heal events recorded in one pytest session.");
  const run = useResource<RunDetail>(`/runs/${runId}`);
  const reduce = useReducedMotion();

  if (run.error) {
    return run.error.status === 404 || run.error.status === 422 ? (
      <EmptyState title="Run not found" action={<ButtonLink to="/runs" variant="secondary">Back to runs</ButtonLink>}>
        No run with id <code className="font-mono">{runId}</code>.
      </EmptyState>
    ) : (
      <ErrorBanner error={run.error} onRetry={run.reload} />
    );
  }
  const data = run.data;
  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton lines={2} className="max-w-md" />
        <div className="grid gap-4 md:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="text-sm text-dim">
        <Link to="/runs" className="hover:underline">Runs</Link>
        <span aria-hidden="true"> / </span>
        <span className="font-mono">{data.run_id}</span>
      </nav>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Run {data.run_id.slice(-8)}</h1>
        <p className="mt-1 text-sm text-muted">
          {new Date(data.started_at).toLocaleString()} · {data.event_count} heal event
          {data.event_count === 1 ? "" : "s"}
          {data.skipped_lines ? ` · ${String(data.skipped_lines)} unreadable event line(s) skipped` : ""}
        </p>
      </header>
      {data.events.length === 0 ? (
        <EmptyState title="No heal events in this run" />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {data.events.map((e, i) => (
            <motion.li
              key={e.id}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: reduce ? 0 : Math.min(i, 8) * 0.04 }}
            >
              <Link
                to={`/events/${e.id}`}
                className="block h-full rounded-3xl border border-line bg-surface p-5 hover:border-accent"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={e.decision.status} />
                  {e.decision.tier ? (
                    <span className="rounded-full bg-chip-hover px-2 py-0.5 text-xs font-semibold">Tier {e.decision.tier}</span>
                  ) : null}
                  <TriageBadge status={e.triage.status} />
                  {e.timings_ms.total !== undefined ? (
                    <span className="ml-auto font-mono text-xs text-dim">{(e.timings_ms.total / 1000).toFixed(2)} s</span>
                  ) : null}
                </div>
                <p className="mt-3 truncate font-mono text-xs text-dim">{e.key.test_nodeid}</p>
                <p className="mt-1 font-mono text-sm">
                  page.{e.key.action}(<span className="text-red-600 line-through dark:text-red-400">{JSON.stringify(e.key.selector)}</span>)
                </p>
                {e.decision.status === "healed" && e.decision.locator ? (
                  <p className="mt-1 truncate font-mono text-sm text-emerald-700 dark:text-emerald-400">→ {e.decision.locator}</p>
                ) : null}
                <p className="mt-2 line-clamp-2 text-sm text-muted">{e.decision.reason}</p>
              </Link>
            </motion.li>
          ))}
        </ul>
      )}
    </div>
  );
}
