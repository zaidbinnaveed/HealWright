import type { CandidatesReport, HealEvent } from "../../api/types";
import { EmptyState } from "../States";

const FEATURES = ["role", "text", "attributes", "ancestors", "neighbors", "geometry"] as const;

function Bar({ value, label }: { value: number | undefined; label: string }) {
  if (value === undefined) {
    return <span className="text-xs text-dim" title={`${label}: not defined for this target`}>n/a</span>;
  }
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2" title={`${label}: ${value.toFixed(3)}`}>
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-chip-hover" aria-hidden="true">
        <div className="accent-gradient h-full rounded-full" style={{ width: `${String(pct)}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-xs tabular-nums">{value.toFixed(2)}</span>
    </div>
  );
}

export function CandidateTable({ event, report }: { event: HealEvent; report: CandidatesReport | null }) {
  if (!report || report.candidates.length === 0) {
    return <EmptyState title="No candidate ranking">This event has no Tier-1 ranking (the heal stopped earlier).</EmptyState>;
  }
  const gate = report.gate;
  const chosen = event.decision.chosen?.index;
  const accepted = event.decision.status === "healed" || event.decision.status === "suggested";
  const attempted = new Map(report.attempts.map((a) => [a.index, a.outcome]));
  return (
    <section aria-labelledby="cands-title" className="rounded-3xl border border-line bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-5 py-3">
        <h2 id="cands-title" className="text-sm font-semibold">Tier-1 candidates (top {report.candidates.length})</h2>
        {gate ? (
          <p className="text-xs text-muted">
            Gate: score ≥ <b>{gate.tau.toFixed(2)}</b> and margin ≥ <b>{gate.delta.toFixed(2)}</b> · this step: margin{" "}
            <b className={gate.margin >= gate.delta ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}>
              {gate.margin.toFixed(3)}
            </b>{" "}
            → {gate.accepted ? "accepted" : "escalated to Tier 2"}
          </p>
        ) : null}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Candidates ranked by Tier-1 score with per-feature scores</caption>
          <thead className="text-xs uppercase tracking-wide text-dim">
            <tr>
              <th scope="col" className="px-5 py-2">#</th>
              <th scope="col" className="px-3 py-2">Element</th>
              <th scope="col" className="px-3 py-2">Score</th>
              {FEATURES.map((f) => (
                <th key={f} scope="col" className="px-3 py-2 capitalize">{f}</th>
              ))}
              <th scope="col" className="px-3 py-2">Sandbox</th>
            </tr>
          </thead>
          <tbody>
            {report.candidates.map((c, i) => {
              const isChosen = c.index === chosen;
              const outcome = attempted.get(c.index);
              return (
                <tr
                  key={c.index}
                  className={`border-t border-line ${isChosen && accepted ? "bg-accent/10" : ""}`}
                  aria-current={isChosen && accepted ? "true" : undefined}
                >
                  <td className="px-5 py-2.5 font-mono text-xs">{i + 1}</td>
                  <td className="px-3 py-2.5">
                    <div className="font-medium">
                      {c.fingerprint.accessible_name || c.fingerprint.text || `<${c.fingerprint.tag}>`}
                      {isChosen ? (
                        accepted ? (
                          <span className="ml-2 rounded bg-ink px-1.5 py-0.5 text-[10px] font-semibold uppercase text-bg">chosen</span>
                        ) : (
                          <span className="ml-2 rounded bg-chip-hover px-1.5 py-0.5 text-[10px] font-semibold uppercase text-muted">last tried</span>
                        )
                      ) : null}
                    </div>
                    <div className="font-mono text-xs text-dim">
                      {c.fingerprint.tag}
                      {c.fingerprint.role ? `[role=${c.fingerprint.role}]` : ""}
                      {c.fingerprint.attributes.id ? `#${c.fingerprint.attributes.id}` : ""}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono font-semibold tabular-nums">{c.score.toFixed(3)}</td>
                  {FEATURES.map((f) => (
                    <td key={f} className="px-3 py-2.5">
                      <Bar value={c.feature_scores[f]} label={f} />
                    </td>
                  ))}
                  <td className="px-3 py-2.5 text-xs">
                    {outcome === undefined ? (
                      <span className="text-dim">–</span>
                    ) : (
                      <span className={outcome === "pass" ? "font-semibold text-emerald-600 dark:text-emerald-400" : "font-semibold text-red-600 dark:text-red-400"}>
                        {outcome}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
