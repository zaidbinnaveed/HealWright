import { useState } from "react";
import type { ApiCall, CandidatesReport, Contract, HealEvent } from "../../api/types";
import { EmptyState } from "../States";

const callKey = (c: ApiCall) => `${c.method} ${c.path_template} ${c.status_class}`;
const STATE_CHANGING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const sign = (n: number) => (n > 0 ? "+1" : n < 0 ? "−1" : "0");

interface Side {
  title: string;
  contract: Contract | null;
}

function Row({ label, a, b }: { label: string; a: string; b: string }) {
  const differ = a !== b;
  return (
    <tr className="border-t border-line">
      <th scope="row" className="py-2 pr-3 text-left text-xs font-medium text-dim">{label}</th>
      <td className="py-2 pr-3 font-mono text-xs">{a}</td>
      <td className={`py-2 font-mono text-xs ${differ ? "font-semibold text-red-600 dark:text-red-400" : ""}`}>
        {b}
        {differ ? <span className="sr-only"> (differs)</span> : null}
      </td>
    </tr>
  );
}

function Calls({ expected, observed }: { expected: Contract; observed: Contract }) {
  const exp = new Set(expected.api_calls.map(callKey));
  const obs = new Set(observed.api_calls.map(callKey));
  const all = [...new Set([...exp, ...obs])].sort();
  if (all.length === 0) return <p className="text-xs text-dim">No same-origin API calls on either side.</p>;
  return (
    <ul className="space-y-1">
      {all.map((k) => {
        const inE = exp.has(k);
        const inO = obs.has(k);
        const method = k.split(" ")[0] ?? "";
        const extra = !inE && inO;
        const missing = inE && !inO;
        const cls = extra
          ? STATE_CHANGING.has(method)
            ? "border-red-300 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
            : "border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30"
          : missing
            ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
            : "border-line";
        return (
          <li key={k} className={`flex items-center justify-between gap-3 rounded-md border px-2.5 py-1.5 font-mono text-xs ${cls}`}>
            <span>{k}</span>
            <span className="font-sans font-semibold">
              {extra ? (STATE_CHANGING.has(method) ? "EXTRA state-changing call" : "extra") : missing ? "missing" : "matches"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Phi_0 (recorded contract) vs Phi_test (what a candidate actually did), per verify attempt. */
export function ContractCompare({ event, report }: { event: HealEvent; report: CandidatesReport | null }) {
  const expected = event.decision.verification?.expected ?? null;
  const sides: Side[] = (report?.attempts ?? []).map((a) => ({
    title: `Candidate "${a.label}" (${a.outcome})`,
    contract: a.observed,
  }));
  if (sides.length === 0 && event.decision.verification?.observed) {
    sides.push({ title: "Observed", contract: event.decision.verification.observed });
  }
  const [pick, setPick] = useState(0);
  if (!expected || sides.length === 0) {
    return (
      <EmptyState title="No behaviour comparison">
        No candidate was replayed in the sandbox, so there is nothing to compare with the recorded effect.
      </EmptyState>
    );
  }
  const side = sides[Math.min(pick, sides.length - 1)];
  const observed = side?.contract ?? null;
  return (
    <section aria-labelledby="phi-title" className="rounded-3xl border border-line bg-surface p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="phi-title" className="text-sm font-semibold">
          Expected vs observed behaviour <span className="font-normal text-dim">(Φ₀ vs Φ_test)</span>
        </h2>
        {sides.length > 1 ? (
          <label className="text-xs">
            <span className="mr-2 text-dim">Attempt</span>
            <select
              value={pick}
              onChange={(e) => { setPick(Number(e.target.value)); }}
              className="rounded-md border border-line-strong bg-surface px-2 py-1"
            >
              {sides.map((s, i) => (
                <option key={s.title} value={i}>{s.title}</option>
              ))}
            </select>
          </label>
        ) : (
          <span className="text-xs text-dim">{side?.title}</span>
        )}
      </div>
      {observed ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <table className="w-full">
            <caption className="sr-only">Recorded contract compared with the observed effect</caption>
            <thead>
              <tr className="text-xs text-dim">
                <th scope="col" className="pb-1 text-left font-medium" />
                <th scope="col" className="pb-1 text-left font-medium">Recorded (Φ₀)</th>
                <th scope="col" className="pb-1 text-left font-medium">Observed (Φ_test)</th>
              </tr>
            </thead>
            <tbody>
              <Row label="URL before" a={expected.url_before} b={observed.url_before} />
              <Row label="URL after" a={expected.url_after} b={observed.url_after} />
              <Row label="Modal Δ" a={sign(expected.modal_delta)} b={sign(observed.modal_delta)} />
              <Row label="DOM Δ sign" a={sign(expected.dom_delta_sign)} b={sign(observed.dom_delta_sign)} />
              <Row label="Strength" a={expected.strength} b={observed.strength} />
            </tbody>
          </table>
          <div>
            <h3 className="mb-2 text-xs font-medium text-dim">Same-origin API calls</h3>
            <Calls expected={expected} observed={observed} />
          </div>
        </div>
      ) : (
        <p className="text-sm text-dim">The sandbox could not observe this attempt (inconclusive).</p>
      )}
    </section>
  );
}
