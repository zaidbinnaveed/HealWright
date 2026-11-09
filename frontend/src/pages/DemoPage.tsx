import { motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiError, postJson, request, useResource } from "../api/client";
import type { DemoRun, DemoStage, DevScenario } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { Button, SendIcon } from "../components/ui/Button";
import { SectionHeader } from "../components/ui/Cards";
import { Checkbox, Spinner } from "../components/ui/Feedback";
import { Stepper } from "../components/ui/Navigation";
import { useToast } from "../components/ui/toast-context";
import { EmptyState, ErrorBanner, SkeletonCard } from "../components/States";
import { useFeatures } from "../lib/useFeatures";
import { useTitle } from "../lib/useTitle";

const STEPS: { stage: DemoStage; label: string; detail: string }[] = [
  { stage: "starting_store", label: "Start the store", detail: "Chaos Store, control routes on" },
  { stage: "recording_baselines", label: "Record baselines", detail: "2 clean runs: fingerprints and behaviour contract" },
  { stage: "breaking", label: "Break the page", detail: "apply the scenario's mutation" },
  { stage: "running_test", label: "Run the test", detail: "HealWright in heal mode (replay)" },
  { stage: "done", label: "Verdict", detail: "classified from the store's action log" },
];
const ORDER: DemoStage[] = ["queued", ...STEPS.map((s) => s.stage)];

const FEATURED = ["dev-01-id-rename", "dev-07-distractor", "dev-09-regression"];

const VERDICT = {
  true_heal: {
    title: "Healed",
    text: "The test passed and the intended action fired: the right element was found and verified.",
    cls: "border-emerald-500/40 bg-emerald-500/10 text-ink",
  },
  red: {
    title: "Stayed red (failed closed)",
    text: "HealWright did not change the outcome: the original Playwright error was re-raised.",
    cls: "border-line-strong bg-chip text-ink",
  },
  false_heal: {
    title: "False heal",
    text: "An action fired that the clean run never fired. This is the failure HealWright is built to prevent.",
    cls: "border-red-500/40 bg-red-500/10 text-ink",
  },
} as const;

function expectation(s: DevScenario): string {
  if (s.class === "distractor_trap") return "A look-alike button sits next to the real one: the verifier must not pick it.";
  if (s.class === "regression_trap") return "The feature was really removed: the test must stay red.";
  return "A harmless UI change broke the locator: the test should heal.";
}

function asApiError(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e), null);
}

/** A demo is running for someone else, or this visitor must wait a moment (public demo). */
function BusyNotice({ error, onReady }: { error: ApiError; onReady: () => void }) {
  const cooldown = error.code === "DEMO_COOLDOWN";
  const match = /(\d+) s/.exec(error.message);
  const [left, setLeft] = useState(cooldown && match ? Number(match[1]) : 0);
  useEffect(() => {
    if (!cooldown) {
      const t = window.setTimeout(onReady, 8000);
      return () => {
        window.clearTimeout(t);
      };
    }
    if (left <= 0) {
      onReady();
      return undefined;
    }
    const t = window.setTimeout(() => {
      setLeft((n) => n - 1);
    }, 1000);
    return () => {
      window.clearTimeout(t);
    };
  }, [cooldown, left, onReady]);
  return (
    <div role="status" className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
      <Spinner size={16} label="Waiting" />
      <p>
        {cooldown ? (
          <>
            Thanks for trying HealWright. You can start the next demo in <strong>{left} s</strong>.
          </>
        ) : (
          <>
            <strong>Busy:</strong> another visitor&apos;s demo is running right now. Try again shortly; one demo runs at a time.
          </>
        )}
      </p>
    </div>
  );
}

export function DemoPage() {
  useTitle("Live demo", "Break a page and watch HealWright heal a real Playwright test.");
  const scenarios = useResource<{ items: DevScenario[] }>("/scenarios");
  const [selected, setSelected] = useState<string>(FEATURED[1] ?? "");
  const [run, setRun] = useState<DemoRun | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [starting, setStarting] = useState(false);
  const [watch, setWatch] = useState(false);
  const [opening, setOpening] = useState(false);
  const timer = useRef<number | null>(null);
  const reduce = useReducedMotion();
  const toast = useToast();
  const features = useFeatures();
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const poll = (id: string) => {
    request<DemoRun>(`/demo/runs/${id}`)
      .then((r) => {
        setRun(r);
        if (!r.running) {
          if (r.stage === "done" && r.outcome) toast({ kind: r.outcome === "false_heal" ? "error" : "success", title: `Demo finished: ${VERDICT[r.outcome].title}`, description: r.scenario_id });
          if (r.stage === "error") toast({ kind: "error", title: "Demo run failed", description: r.error ?? undefined });
        }
        if (r.running) {
          timer.current = window.setTimeout(() => {
            poll(id);
          }, 1000);
        }
      })
      .catch((e: unknown) => {
        setError(asApiError(e));
      });
  };

  const start = () => {
    setError(null);
    setRun(null);
    setStarting(true);
    postJson<DemoRun>("/demo/runs", { scenario_id: selected, watch })
      .then((r) => {
        setRun(r);
        poll(r.id);
      })
      .catch((e: unknown) => {
        setError(asApiError(e));
      })
      .finally(() => {
        setStarting(false);
      });
  };

  const openShop = () => {
    setError(null);
    setOpening(true);
    const tab = window.open("about:blank", "_blank");
    postJson<{ url: string }>("/demo/shop", { scenario_id: selected })
      .then((r) => {
        if (tab) {
          tab.opener = null;
          tab.location.href = r.url;
        } else {
          window.open(r.url, "_blank", "noopener");
        }
        toast({ kind: "info", title: "Broken shop opened in a new tab", description: selected });
      })
      .catch((e: unknown) => {
        tab?.close();
        setError(asApiError(e));
      })
      .finally(() => {
        setOpening(false);
      });
  };

  const items = scenarios.data?.items ?? [];
  const featured = FEATURED.map((id) => items.find((s) => s.id === id)).filter((s): s is DevScenario => !!s);
  const current = items.find((s) => s.id === selected);
  const busy = starting || (run?.running ?? false);
  const at = run ? ORDER.indexOf(run.stage) : -1;

  return (
    <div className="space-y-6">
      <SectionHeader as="h1" eyebrow="Live demo" title="Break it," italic="watch it heal">
        Pick a dev scenario, break the page, and watch HealWright run the real test. Model replies come from the replay
        cache, so this works offline. One run at a time.
      </SectionHeader>

      {scenarios.error ? <ErrorBanner error={scenarios.error} onRetry={scenarios.reload} /> : null}
      {scenarios.loading && !scenarios.data ? <SkeletonCard /> : null}
      {scenarios.data && items.length === 0 ? <EmptyState title="No dev scenarios found" /> : null}

      {items.length > 0 ? (
        <section
          aria-labelledby="pick"
          className="rounded-3xl border border-line bg-surface p-5"
        >
          <h2 id="pick" className="text-sm font-semibold">
            1. Pick a scenario
          </h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3" role="radiogroup" aria-label="Featured scenarios">
            {featured.map((s) => (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={selected === s.id}
                disabled={busy}
                onClick={() => {
                  setSelected(s.id);
                }}
                className={`rounded-lg border p-3 text-left text-sm disabled:opacity-60 ${
                  selected === s.id
                    ? "border-accent bg-accent/10"
                    : "border-line hover:border-line-strong"
                }`}
              >
                <span className="font-mono text-xs">{s.id}</span>
                <span className="mt-1 block text-muted">{expectation(s)}</span>
              </button>
            ))}
          </div>
          <label className="mt-4 flex flex-wrap items-center gap-2 text-sm text-muted">
            Or any dev scenario
            <select
              value={selected}
              disabled={busy}
              onChange={(e) => {
                setSelected(e.target.value);
              }}
              className="rounded-lg border border-line-strong bg-surface px-2 py-1 font-mono text-sm text-ink"
            >
              {items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id}
                </option>
              ))}
            </select>
          </label>
          {current ? (
            <p className="mt-2 text-xs text-dim">
              Test <code className="font-mono">{current.test}</code> · expected{" "}
              <code className="font-mono">{current.expected_outcome}</code>
            </p>
          ) : null}
          <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
            <Button onClick={start} disabled={busy || !current} icon={busy ? <Spinner size={16} label="Running" /> : <SendIcon />}>
              {busy ? "Running…" : "2. Break it and run the test"}
            </Button>
            <Button variant="secondary" onClick={openShop} disabled={!current || opening}>
              Open the broken shop
            </Button>
            {features?.watch ? (
              <Checkbox checked={watch} onChange={setWatch}>
                Watch it happen (opens a browser window, slowed down)
              </Checkbox>
            ) : null}
          </div>
        </section>
      ) : null}

      {error && (error.code === "DEMO_BUSY" || error.code === "DEMO_COOLDOWN") ? (
        <BusyNotice error={error} onReady={clearError} />
      ) : error ? (
        <ErrorBanner error={error} onRetry={start} />
      ) : null}

      {run ? (
        <section
          aria-labelledby="progress"
          aria-live="polite"
          className="rounded-3xl border border-line bg-surface p-5"
        >
          <div className="flex items-baseline justify-between">
            <h2 id="progress" className="text-sm font-semibold">
              3. Progress <span className="font-mono text-xs font-normal">{run.scenario_id}</span>
            </h2>
            <span className="font-mono text-xs tabular-nums text-dim">{run.elapsed_s.toFixed(1)} s</span>
          </div>
          <div className="mt-6 overflow-x-auto">
            <div className="min-w-[560px]">
              <Stepper
                steps={STEPS.map((st) => ({ label: st.label, detail: st.detail }))}
                current={run.stage === "done" ? STEPS.length : run.stage === "error" ? STEPS.length - 1 : Math.max(0, at - 1)}
                failed={run.stage === "error"}
              />
            </div>
          </div>

          {run.stage === "error" ? (
            <div
              role="alert"
              className="mt-6 rounded-2xl border border-red-500/40 bg-red-500/5 p-4 text-sm"
            >
              <p className="font-semibold">The demo run failed</p>
              <p className="mt-1 font-mono text-xs">{run.error}</p>
            </div>
          ) : null}

          <Shots run={run} />

          {run.stage === "done" && run.outcome ? (
            <motion.div
              data-testid="verdict"
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`mt-6 rounded-2xl border p-5 ${VERDICT[run.outcome].cls}`}
            >
              <p className="text-lg font-semibold">{VERDICT[run.outcome].title}</p>
              <p className="mt-1 text-sm">{VERDICT[run.outcome].text}</p>
              <dl className="mt-3 grid gap-2 text-xs md:grid-cols-3">
                <div>
                  <dt className="opacity-75">Test</dt>
                  <dd className="font-semibold">{run.test_passed ? "passed" : "failed"}</dd>
                </div>
                <div>
                  <dt className="opacity-75">Expected action</dt>
                  <dd className="font-mono">{run.expected_action ?? "n/a"}</dd>
                </div>
                <div>
                  <dt className="opacity-75">Actions fired</dt>
                  <dd className="font-mono">{run.fired_actions.length ? run.fired_actions.join(", ") : "none"}</dd>
                </div>
              </dl>
              {run.heal_events && run.heal_events.length > 0 ? (
                <ul className="mt-4 space-y-2">
                  {run.heal_events.map((e) => (
                    <li
                      key={e.id}
                      className="flex flex-wrap items-center gap-3 rounded-lg bg-surface/70 p-2 text-sm"
                    >
                      <StatusBadge status={e.decision.status} />
                      <span className="font-mono text-xs">{e.key.selector}</span>
                      <Link
                        to={`/events/${e.id}`}
                        className="ml-auto font-medium text-accent-ink underline"
                      >
                        Open heal event
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-xs opacity-75">No heal event was recorded.</p>
              )}
            </motion.div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function Shots({ run }: { run: DemoRun }) {
  const reduce = useReducedMotion();
  const failure = run.heal_events?.find((e) => e.artifact_urls.before)?.artifact_urls.before;
  const items = [
    { key: "clean", label: "Clean run: how the page should end", src: run.shots?.includes("clean") ? `/api/v1/demo/runs/${run.id}/shots/clean` : null },
    { key: "failure", label: "At failure: the broken page", src: failure ?? null },
    { key: "healed", label: "After heal: how the healed run ended", src: run.shots?.includes("healed") ? `/api/v1/demo/runs/${run.id}/shots/healed` : null },
  ];
  if (!items.some((i) => i.src)) return null;
  return (
    <div className="mt-4 grid gap-3 md:grid-cols-3" aria-label="Screenshots">
      {items.map((i) => (
        <figure key={i.key} className="overflow-hidden rounded-lg border border-line bg-chip">
          <div className="relative aspect-[16/10] bg-bg">
            {i.src ? (
              <motion.img
                src={i.src}
                alt={i.label}
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                className="absolute inset-0 h-full w-full object-contain"
              />
            ) : (
              <div role="status" aria-label={`${i.label}: waiting`} className="absolute inset-0 animate-pulse bg-ink/5" />
            )}
          </div>
          <figcaption className="px-3 py-2 text-xs text-muted">{i.label}</figcaption>
        </figure>
      ))}
    </div>
  );
}
