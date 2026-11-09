import type { CandidatesReport, HealEvent } from "../../api/types";
import { Card } from "../ui/Cards";
import { Timeline as UiTimeline } from "../ui/Navigation";

type State = "pass" | "fail" | "skip" | "info";

interface Stage {
  key: string;
  title: string;
  detail: string;
  state: State;
  ms: number | undefined;
}

function fmt(ms: number | undefined): string {
  if (ms === undefined) return "";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(0)} ms`;
}

function buildStages(event: HealEvent, report: CandidatesReport | null): Stage[] {
  const d = event.decision;
  const t = event.timings_ms;
  const gate = report?.gate ?? null;
  const attempts = report?.attempts ?? [];
  const tier2Used = d.tier === 2 || t.tier2 !== undefined;
  const stages: Stage[] = [
    {
      key: "tier1",
      title: "Tier 1: deterministic scorer + margin gate",
      detail: gate
        ? `${String(gate.compatible_candidates)} compatible candidates; top ${gate.top_score?.toFixed(3) ?? "–"}, margin ${gate.margin.toFixed(3)} (needs ≥ ${gate.tau.toFixed(2)} and ≥ ${gate.delta.toFixed(2)}): ${gate.accepted ? "accepted" : "escalated"}`
        : "No ranking recorded",
      state: gate ? (gate.accepted ? "pass" : "info") : "skip",
      ms: (t.extract ?? 0) + (t.tier1 ?? 0) || undefined,
    },
    {
      key: "tier2",
      title: "Tier 2: vision model picks a mark",
      detail: tier2Used
        ? d.tier === 2
          ? "The VLM chose a candidate by mark id (never code)"
          : "Tier 2 did not return a usable pick"
        : "Not needed: Tier 1 was confident",
      state: tier2Used ? (d.tier === 2 ? "pass" : "fail") : "skip",
      ms: t.tier2,
    },
    {
      key: "verify",
      title: "Sandbox verification",
      detail: attempts.length
        ? attempts
            .map((a) => `"${a.label}": ${a.outcome}${a.mismatches.length ? ` (${a.mismatches.join("; ")})` : ""}`)
            .join(" · ")
        : "No candidate was replayed in the sandbox",
      state: attempts.some((a) => a.outcome === "pass") ? "pass" : attempts.length ? "fail" : "skip",
      ms: t.verify,
    },
    {
      key: "live",
      title: "Live re-check",
      detail: report?.live_check
        ? report.live_check.outcome === "pass"
          ? "The real page produced the recorded effect again"
          : `Failed: ${report.live_check.mismatches.join("; ")}`
        : "Not run (no verified candidate)",
      state: report?.live_check ? (report.live_check.outcome === "pass" ? "pass" : "fail") : "skip",
      ms: t.live,
    },
    {
      key: "patch",
      title: "Patch",
      detail: event.diff
        ? "Unified diff generated and checked with git apply --check"
        : event.artifacts.suggestion
          ? "Call site not patchable: suggestion text saved"
          : "No patch",
      state: event.diff ? "pass" : "skip",
      ms: t.patch,
    },
  ];
  return stages;
}

export function Timeline({ event, report }: { event: HealEvent; report: CandidatesReport | null }) {
  const stages = buildStages(event, report);
  const tone = { pass: "ok", fail: "bad", skip: "skip", info: "neutral" } as const;
  const icon = { pass: "✓", fail: "✕", skip: "–", info: "→" } as const;
  return (
    <Card as="section" className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 id="timeline-title" className="text-sm font-semibold">Decision timeline</h2>
        {event.timings_ms.total !== undefined ? <span className="text-xs text-dim">total {fmt(event.timings_ms.total)}</span> : null}
      </div>
      <UiTimeline
        items={stages.map((s) => ({
          key: s.key,
          title: s.title,
          meta: fmt(s.ms),
          tone: tone[s.state],
          icon: <span className="text-xs font-semibold">{icon[s.state]}<span className="sr-only"> ({s.state})</span></span>,
          children: s.detail,
        }))}
      />
    </Card>
  );
}
