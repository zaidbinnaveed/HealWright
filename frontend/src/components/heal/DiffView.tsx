import type { PatchView } from "../../api/types";
import { TerminalCard } from "../ui/Cards";

function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-zinc-500";
  if (line.startsWith("@@")) return "text-sky-300";
  if (line.startsWith("+")) return "bg-emerald-500/10 text-green-300";
  if (line.startsWith("-")) return "bg-red-500/10 text-red-300";
  return "text-zinc-300";
}

/** Minimal Python token colouring for the code part of a diff line (strings, keywords). */
function Code({ text }: { text: string }) {
  const parts = text.split(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g);
  return (
    <>
      {parts.map((p, i) =>
        /^["']/.test(p) ? (
          <span key={i} className="text-amber-300">{p}</span>
        ) : (
          <span key={i}>
            {p.split(/\b(def|with|lambda|and|or|return|import|from|True|False|None)\b/g).map((w, j) =>
              /^(def|with|lambda|and|or|return|import|from|True|False|None)$/.test(w) ? (
                <span key={j} className="font-semibold text-fuchsia-300">{w}</span>
              ) : (
                w
              ),
            )}
          </span>
        ),
      )}
    </>
  );
}

export function DiffView({ patch }: { patch: PatchView }) {
  const lines = patch.diff.replace(/\n$/, "").split("\n");
  return (
    <section aria-labelledby="diff-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="diff-title" className="text-sm font-semibold">
          Patch <span className="font-mono font-normal text-dim">{patch.source_path}</span>
        </h2>
        <div className="flex gap-2 text-xs">
          <span className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-chip px-2.5 py-0.5 font-medium`}>
            <span aria-hidden="true" className="uv-dot" style={{ ["--background-tooltip-container" as string]: patch.apply_check.ok ? "#10b981" : "#ef4444" }} />
            git apply --check: {patch.apply_check.ok ? "ok" : "fails"}
          </span>
          {patch.source_changed ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-chip px-2.5 py-0.5 font-medium">
              <span aria-hidden="true" className="uv-dot" style={{ ["--background-tooltip-container" as string]: "#f59e0b" }} />
              source changed since the heal
            </span>
          ) : null}
        </div>
      </div>
      <TerminalCard title={patch.source_path?.split("/").pop() ?? "patch.diff"}>
        <pre className="-mx-6 overflow-x-auto text-xs leading-5" aria-label="Unified diff">
          <code>
            {lines.map((line, i) => (
              <div key={i} className={`px-6 font-mono ${lineClass(line)}`}>
                <span aria-hidden="true" className="mr-3 inline-block w-3 select-none text-zinc-500">
                  {line.startsWith("+") && !line.startsWith("+++") ? "+" : line.startsWith("-") && !line.startsWith("---") ? "−" : ""}
                </span>
                {line.startsWith("@@") || line.startsWith("+++") || line.startsWith("---") ? line : <Code text={line.slice(1)} />}
              </div>
            ))}
          </code>
        </pre>
      </TerminalCard>
    </section>
  );
}
