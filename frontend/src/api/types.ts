// Types for /api/v1 (docs/API.md). They mirror src/healwright/models.py and the
// candidates.json artifact written by the healer. Keep in sync with the backend.

export type HealStatus =
  | "healed"
  | "suggested"
  | "needs_human"
  | "regression_suspected"
  | "not_a_locator_failure"
  | "error";

export type TriageStatus = "pending" | "accepted" | "rejected" | "applied";

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Fingerprint {
  schema_version: 1;
  role: string | null;
  accessible_name: string;
  tag: string;
  text: string;
  attributes: Record<string, string>;
  class_tokens: string[];
  ancestor_path: string[];
  neighbor_texts: string[];
  bbox: BBox;
  viewport: [number, number];
  in_shadow_dom: boolean;
}

export interface ApiCall {
  method: string;
  path_template: string;
  status_class: string;
}

export interface Contract {
  url_before: string;
  url_after: string;
  api_calls: ApiCall[];
  modal_delta: -1 | 0 | 1;
  dom_delta_sign: -1 | 0 | 1;
  strength: "strong" | "weak" | "none";
  observations: number;
}

export interface Candidate {
  index: number;
  fingerprint: Fingerprint;
  score: number;
  feature_scores: Record<string, number>;
}

export interface Verification {
  outcome: "pass" | "fail" | "inconclusive" | "skipped";
  expected: Contract;
  observed: Contract | null;
  mismatches: string[];
}

export interface Decision {
  status: HealStatus;
  tier: 1 | 2 | null;
  chosen: Candidate | null;
  locator: string | null;
  verification: Verification | null;
  reason: string;
}

export interface StepKey {
  test_nodeid: string;
  action: string;
  selector: string;
  occurrence: number;
}

export interface Triage {
  status: TriageStatus;
  decision: "accepted" | "rejected" | null;
  note: string;
  applied: boolean;
  updated_at: string | null;
}

export type ArtifactName = "before" | "som" | "patch" | "suggestion" | "candidates";

export interface HealEvent {
  schema_version: 1;
  id: string;
  run_id: string;
  key: StepKey;
  decision: Decision;
  timings_ms: Record<string, number>;
  artifacts: Partial<Record<ArtifactName, string>>;
  diff: string | null;
  source_sha256: string | null;
  triage_status: string;
  triage: Triage;
  artifact_urls: Partial<Record<ArtifactName, string>>;
}

export interface Gate {
  accepted: boolean;
  top_score: number | null;
  second_score: number | null;
  margin: number;
  reason: string;
  tau: number;
  delta: number;
  tier2_floor: number;
  compatible_candidates: number;
}

export interface Attempt {
  index: number;
  label: string;
  strategy: string;
  locator: string;
  outcome: Verification["outcome"];
  mismatches: string[];
  observed: Contract | null;
}

export interface CandidatesReport {
  schema_version: 1;
  gate: Gate | null;
  candidates: Candidate[];
  attempts: Attempt[];
  live_check: { outcome: string; mismatches: string[]; observed: Contract } | null;
}

export interface PatchView {
  event_id: string;
  diff: string;
  source_path: string | null;
  source_sha256: string | null;
  current_sha256: string | null;
  source_changed: boolean;
  apply_check: { ok: boolean; message: string };
}

export interface RunSummary {
  run_id: string;
  started_at: string;
  event_count: number;
  status_counts: Record<HealStatus, number>;
  tier_counts: { "1": number; "2": number };
  tests: string[];
  skipped_lines: number;
}

export interface RunDetail extends RunSummary {
  events: HealEvent[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string; details?: unknown[] };
}

// /api/v1/benchmarks/combined (final eval summary written by benchmark.combine)
export interface Stat {
  values: (number | null)[];
  mean: number | null;
  min: number | null;
  max: number | null;
}

export type Outcome = "true_heal" | "false_heal" | "red" | "error";

export interface ClassCounts {
  scored: number;
  true_heal: number;
  false_heal: number;
  red: number;
}

export interface CombinedSystem {
  system: string;
  split: string;
  runs: number;
  summary: Record<string, Stat | undefined>;
  per_run: { id: string; vlm_mode: string | null; started_at: string | null }[];
  by_class: Record<string, ClassCounts>;
}

export interface CombinedScenario {
  id: string;
  class: string;
  expected: string;
  outcomes: Record<string, Outcome[]>;
}

export interface CombinedBenchmark {
  systems: CombinedSystem[];
  scenarios: CombinedScenario[];
}

// /api/v1/scenarios and /api/v1/demo/runs (dev split only)
export interface DevScenario {
  id: string;
  class: string;
  test: string;
  expected_outcome: string;
  expected_action: string;
}

export type DemoStage =
  | "queued"
  | "starting_store"
  | "recording_baselines"
  | "breaking"
  | "running_test"
  | "done"
  | "error";

export interface DemoRun {
  id: string;
  scenario_id: string;
  stage: DemoStage;
  running: boolean;
  elapsed_s: number;
  outcome: "true_heal" | "false_heal" | "red" | null;
  test_passed: boolean | null;
  fired_actions: string[];
  expected_action: string | null;
  heal_event_ids: string[];
  run_ids: string[];
  error: string | null;
  watch?: boolean;
  shots?: string[];
  heal_events?: HealEvent[];
}
