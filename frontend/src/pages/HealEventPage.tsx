import { ButtonLink } from "../components/ui/Button";
import { Link, useParams } from "react-router";
import { useResource } from "../api/client";
import type { CandidatesReport, HealEvent, PatchView } from "../api/types";
import { CandidateTable } from "../components/heal/CandidateTable";
import { ContractCompare } from "../components/heal/ContractCompare";
import { DiffView } from "../components/heal/DiffView";
import { Screenshots } from "../components/heal/Screenshots";
import { Timeline } from "../components/heal/Timeline";
import { TriageActions } from "../components/heal/TriageActions";
import { EmptyState, ErrorBanner, Skeleton, SkeletonCard } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { useTitle } from "../lib/useTitle";

/** Artifacts are served under /api/v1/...; the resource hook prefixes /api/v1 itself. */
const rel = (url: string | undefined) => (url ? url.replace(/^\/api\/v1/, "") : null);

export function HealEventPage() {
  useTitle("Heal event", "How HealWright decided on one broken step.");
  const { eventId = "" } = useParams();
  const ev = useResource<HealEvent>(`/heal-events/${eventId}`);
  const event = ev.data;
  const report = useResource<CandidatesReport>(event ? rel(event.artifact_urls.candidates) : null);
  const patch = useResource<PatchView>(event?.diff ? `/heal-events/${eventId}/patch` : null);

  if (ev.error) {
    return ev.error.status === 404 ? (
      <EmptyState title="Heal event not found" action={<ButtonLink to="/runs" variant="secondary">Back to runs</ButtonLink>}>
        No heal event with id <code className="font-mono">{eventId}</code>.
      </EmptyState>
    ) : (
      <ErrorBanner error={ev.error} onRetry={ev.reload} />
    );
  }
  if (!event) {
    return (
      <div className="space-y-6">
        <Skeleton lines={2} className="max-w-xl" />
        <div className="grid gap-6 lg:grid-cols-3">
          <SkeletonCard className="lg:col-span-2" />
          <SkeletonCard />
        </div>
        <SkeletonCard />
      </div>
    );
  }

  const d = event.decision;
  const hasReplacement = d.status === "healed" || d.status === "suggested";
  const reportData = report.data;
  return (
    <article className="space-y-6">
      <nav aria-label="Breadcrumb" className="text-sm text-dim">
        <Link to="/runs" className="hover:underline">Runs</Link>
        <span aria-hidden="true"> / </span>
        <Link to={`/runs/${event.run_id}`} className="font-mono hover:underline">{event.run_id.slice(-8)}</Link>
        <span aria-hidden="true"> / </span>
        <span className="font-mono">{event.id.slice(-8)}</span>
      </nav>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={d.status} />
          {d.tier ? <span className="rounded-full bg-chip-hover px-2.5 py-0.5 text-xs font-semibold">Tier {d.tier}</span> : null}
          <span className="font-mono text-xs text-dim">{event.key.test_nodeid}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">
          <span className="font-mono text-lg">page.{event.key.action}(</span>
          <span className="font-mono text-lg text-red-600 line-through decoration-2 dark:text-red-400">{JSON.stringify(event.key.selector)}</span>
          <span className="font-mono text-lg">)</span>
          <span aria-hidden="true" className="mx-3 text-dim">→</span>
          {hasReplacement && d.locator ? (
            <>
              <span className="sr-only">{d.status === "healed" ? " healed to " : " suggested: "}</span>
              <span className={`font-mono text-lg ${d.status === "healed" ? "text-emerald-700 dark:text-emerald-400" : "text-sky-700 dark:text-sky-400"}`}>{d.locator}</span>
            </>
          ) : (
            <span className="text-lg font-medium text-dim">no verified replacement: the test stays red</span>
          )}
        </h1>
        <p className="max-w-3xl text-sm text-muted">{d.reason}</p>
      </header>

      {report.error && report.error.status !== 404 ? <ErrorBanner error={report.error} onRetry={report.reload} /> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Screenshots event={event} />
        </div>
        <div className="space-y-6">
          <Timeline event={event} report={reportData} />
          <TriageActions event={event} onChange={() => { ev.reload(); patch.reload(); }} />
        </div>
      </div>

      {report.loading ? <SkeletonCard /> : <CandidateTable event={event} report={reportData} />}
      {report.loading ? <SkeletonCard /> : <ContractCompare event={event} report={reportData} />}

      {event.diff ? (
        patch.error ? (
          <ErrorBanner error={patch.error} onRetry={patch.reload} />
        ) : patch.data ? (
          <DiffView patch={patch.data} />
        ) : (
          <SkeletonCard />
        )
      ) : (
        <EmptyState title="No patch for this event">
          {event.artifacts.suggestion
            ? "The call site could not be patched automatically; a suggestion text was saved instead."
            : "Only verified heals produce a patch."}
        </EmptyState>
      )}
    </article>
  );
}
