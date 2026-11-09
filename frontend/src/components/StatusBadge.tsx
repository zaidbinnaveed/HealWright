import type { HealStatus, TriageStatus } from "../api/types";

const STATUS: Record<HealStatus, { label: string; dot: string }> = {
  healed: { label: "Healed", dot: "#10b981" },
  suggested: { label: "Suggested", dot: "#38bdf8" },
  needs_human: { label: "Needs human", dot: "#f59e0b" },
  regression_suspected: { label: "Regression suspected", dot: "#ef4444" },
  not_a_locator_failure: { label: "Not a locator failure", dot: "#a1a1aa" },
  error: { label: "Error", dot: "#d946ef" },
};

const TRIAGE: Record<TriageStatus, string> = {
  pending: "#a1a1aa",
  accepted: "#10b981",
  rejected: "#ef4444",
  applied: "#34d399",
};

function Pill({ dot, children, className = "" }: { dot: string; children: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-chip px-2.5 py-0.5 text-xs font-medium text-ink ${className}`}>
      <span aria-hidden="true" className="uv-dot" style={{ ["--background-tooltip-container" as string]: dot }} />
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: HealStatus }) {
  const s = STATUS[status];
  return <Pill dot={s.dot}>{s.label}</Pill>;
}

export function TriageBadge({ status }: { status: TriageStatus }) {
  return (
    <Pill dot={TRIAGE[status]} className="capitalize">
      {status}
    </Pill>
  );
}
