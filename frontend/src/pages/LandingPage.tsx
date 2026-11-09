import { motion, useInView, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useResource } from "../api/client";
import type { CombinedBenchmark, Stat } from "../api/types";
import { PrismCanvas } from "../components/landing/PrismCanvas";
import { Logo } from "../components/Layout";
import { useTheme } from "../hooks/useTheme";
import { ButtonLink, SendIcon } from "../components/ui/Button";
import { Card, SectionHeader, StatCard, TerminalCard } from "../components/ui/Cards";
import { ThemeToggle } from "../components/ui/Inputs";
import { DotTabs, Stepper } from "../components/ui/Navigation";
import { useToast } from "../components/ui/toast-context";
import { useTitle } from "../lib/useTitle";

const COMMANDS = {
  record: { label: "Record", cmd: "pytest --healwright-mode=record" },
  heal: { label: "Heal", cmd: "pytest --healwright-mode=heal" },
  apply: { label: "Apply", cmd: "healwright apply <event_id>" },
  serve: { label: "Serve", cmd: "healwright serve" },
} as const;
type Cmd = keyof typeof COMMANDS;

function Hero() {
  const [tab, setTab] = useState<Cmd>("heal");
  const [swap, setSwap] = useState(false);
  const [shown, setShown] = useState<Cmd>("heal");
  const [copied, setCopied] = useState(false);
  const [menu, setMenu] = useState(false);
  const [dark, toggle] = useTheme();
  const copyRef = useRef<HTMLDivElement>(null);
  const toast = useToast();

  const pick = (t: Cmd) => {
    setTab(t);
    setSwap(true);
    window.setTimeout(() => {
      setShown(t);
      setSwap(false);
    }, 160);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(COMMANDS[shown].cmd);
      setCopied(true);
      window.setTimeout(() => {
        setCopied(false);
      }, 1400);
      toast({ kind: "success", title: "Command copied", description: COMMANDS[shown].cmd });
    } catch {
      toast({ kind: "error", title: "Could not copy", description: "The browser blocked clipboard access." });
    }
  };
  const links = [
    { to: "/runs", label: "Dashboard" },
    { to: "/benchmarks", label: "Benchmark" },
    { to: "/demo", label: "Live demo" },
  ];

  return (
    <section aria-label="HealWright" className="dark relative isolate min-h-[max(100svh,720px)] overflow-hidden bg-bg text-ink md:min-h-svh">
      <div className="absolute inset-0 -z-10">
        <PrismCanvas copyRef={copyRef} />
        {/* readability scrim behind the copy (left side) */}
        <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_55%_60%_at_18%_55%,rgba(21,21,23,.88),rgba(21,21,23,.55)_55%,transparent_80%)]" />
      </div>
      <header className="relative z-20 flex h-16 items-center justify-between px-[var(--gutter)] py-3.5">
        <div className="flex items-center gap-3.5">
          <Link to="/" aria-label="HealWright home">
            <Logo />
          </Link>
          <nav aria-label="Site" className="ml-3 hidden gap-5 md:flex">
            {links.map((l) => (
              <Link key={l.to} to={l.to} className="text-sm text-muted transition-colors hover:text-ink">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/demo"
            className="hidden h-9 min-w-[172px] items-center justify-between gap-7 rounded-lg border border-line bg-chip pr-1.5 pl-3 text-sm text-muted transition-colors hover:border-line-strong hover:text-ink md:flex"
          >
            Try the demo
            <kbd className="rounded-[5px] border border-line bg-white/[0.03] px-1.5 py-0.5 font-sans text-[11px] text-muted">replay</kbd>
          </Link>
          <ButtonLink to="/runs" className="hidden md:inline-flex" icon={<SendIcon />}>
            Open dashboard
          </ButtonLink>
          <ThemeToggle dark={dark} onToggle={toggle} />
          <button
            type="button"
            aria-label="Open menu"
            aria-expanded={menu}
            onClick={() => {
              setMenu((m) => !m);
            }}
            className="grid size-9 place-items-center rounded-lg hover:bg-white/[0.06] md:hidden"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
              <path d="M4 8h16M4 16h16" />
            </svg>
          </button>
        </div>
      </header>
      {menu ? (
        <nav aria-label="Site (mobile)" className="relative z-20 mx-[var(--gutter)] rounded-xl border border-line bg-bg-2 p-2 md:hidden">
          {links.map((l) => (
            <Link key={l.to} to={l.to} className="block rounded-lg px-3 py-2 text-sm hover:bg-chip">
              {l.label}
            </Link>
          ))}
        </nav>
      ) : null}
      <div
        ref={copyRef}
        className="pointer-events-none relative z-10 flex max-w-[600px] flex-col justify-start px-[var(--gutter)] pt-[clamp(28px,7svh,64px)] md:min-h-[calc(100svh-64px)] md:justify-center md:pt-0 md:pb-16 [&>*]:pointer-events-auto"
      >
        <h1 className="mb-[clamp(14px,1.8vw,22px)] animate-rise font-serif text-[clamp(64px,8vw,116px)] leading-[0.9] font-normal tracking-[-0.035em]">
          HealWright
        </h1>
        <p className="mb-[clamp(24px,2.6vw,36px)] animate-rise text-[clamp(26px,2.9vw,42px)] leading-[1.2] tracking-[-0.025em] [animation-delay:.08s]">
          <span className="block">Broken locators, healed.</span>
          <span className="block text-muted">Never a fake pass.</span>
        </p>
        <div className="mb-3.5 animate-rise [animation-delay:.16s]">
          <DotTabs
            label="Command"
            value={tab}
            onChange={pick}
            tabs={(Object.keys(COMMANDS) as Cmd[]).map((k) => ({ value: k, label: COMMANDS[k].label }))}
          />
        </div>
        <div className="relative flex max-w-[440px] animate-rise items-center justify-between gap-3 pt-3.5 text-[15px] leading-normal [animation-delay:.24s] before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-[linear-gradient(90deg,rgba(255,255,255,.28),rgba(255,255,255,.08)_70%,transparent)]">
          <code className={`font-mono text-sm transition-[opacity,transform] duration-200 ${swap ? "translate-y-[3px] opacity-0" : ""}`}>
            {COMMANDS[shown].cmd}
          </code>
          <button
            type="button"
            aria-label="Copy command"
            onClick={() => {
              void copy();
            }}
            className="grid size-[30px] place-items-center rounded-[7px] text-dim transition-colors hover:bg-white/[0.06] hover:text-ink"
          >
            <svg viewBox="0 0 24 24" className="h-[15px] w-[15px]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {copied ? <path d="m5 12.5 4.5 4.5L19 7.5" /> : <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 012-2h8" /></>}
            </svg>
          </button>
        </div>
      </div>
    </section>
  );
}

const pct = (st: Stat | undefined) => (st?.mean == null ? "n/a" : `${(st.mean * 100).toFixed(1).replace(/\.0$/, "")}%`);
const count = (st: Stat | undefined) => (st?.mean == null ? "n/a" : String(Number(st.mean.toFixed(2))));

function Metrics() {
  const { data, error, loading } = useResource<CombinedBenchmark>("/benchmarks/combined");
  const hw = data?.systems.find((s) => s.system === "healwright");
  const greedy = data?.systems.find((s) => s.system === "greedy");
  const raw = data?.systems.find((s) => s.system === "rawhtml");
  return (
    <section aria-labelledby="results" className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionHeader id="results" eyebrow="Results" title="Measured on the Chaos" italic="Benchmark">
          50 frozen scenarios: 40 healable UI changes and 10 traps that must stay red.
        </SectionHeader>
        <ButtonLink to="/benchmarks" variant="secondary" className="ring-gradient">
          Full results →
        </ButtonLink>
      </div>
      {loading ? (
        <div role="status" aria-label="Loading metrics" className="grid gap-5 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-44 animate-pulse rounded-xl bg-ink/10" />
          ))}
        </div>
      ) : error || !hw ? (
        <p className="rounded-3xl border border-dashed border-line p-5 text-sm text-muted">
          Benchmark numbers are unavailable right now. See the <Link to="/benchmarks" className="underline">benchmark page</Link>.
        </p>
      ) : (
        <div className="grid gap-5 sm:grid-cols-3">
          <StatCard value={pct(hw.summary.true_heal_rate)} label="true heal rate" caption={`eval split, mean of ${String(hw.runs)} runs`} />
          <StatCard
            value={count(hw.summary.false_heals_on_traps)}
            label="false heals on traps"
            caption={`greedy matcher ${count(greedy?.summary.false_heals_on_traps)} · raw-HTML LLM ${count(raw?.summary.false_heals_on_traps)}`}
          />
          <StatCard value={pct(hw.summary.tier1_share_of_heals)} label="heals without a model call" caption="decided by Tier 1" />
        </div>
      )}
    </section>
  );
}

const HOW = [
  { label: "Record", detail: "fingerprints + network contract on green runs" },
  { label: "Match", detail: "Tier 1 scores every visible candidate" },
  { label: "Gate", detail: "clear winner, or ask a vision model (Tier 2)" },
  { label: "Verify", detail: "replay in a sandbox: same API calls?" },
  { label: "Patch", detail: "diff checked with git apply --check" },
];

function HowItWorks() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.4 });
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? HOW.length : 0);
  useEffect(() => {
    if (!inView || reduce) return;
    const t = window.setInterval(() => {
      setStep((s) => (s >= HOW.length ? 0 : s + 1));
    }, 1300);
    return () => {
      window.clearInterval(t);
    };
  }, [inView, reduce]);
  return (
    <section ref={ref} aria-labelledby="how" className="space-y-10">
      <SectionHeader id="how" eyebrow="How it works" title="Five steps, each one" italic="checkable">
        When a locator breaks, the test pauses at that step while HealWright finds, proves and patches the replacement.
      </SectionHeader>
      <Card className="overflow-x-auto px-6 py-8">
        <div className="min-w-[640px]">
          <Stepper steps={HOW} current={step} />
        </div>
      </Card>
    </section>
  );
}

function Features() {
  const bars = [
    { name: "Add to basket", score: 0.93, chosen: true },
    { name: "Save for later", score: 0.41 },
    { name: "Compare", score: 0.22 },
  ];
  return (
    <section aria-labelledby="features" className="space-y-10">
      <SectionHeader id="features" eyebrow="Why it is safe" title="Heals you can" italic="trust">
        Every heal is proven against the behaviour recorded on a green run. When HealWright is not sure, the test stays red.
      </SectionHeader>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-12 md:gap-6">
        <Card as="article" className="md:col-span-7">
          <h3 className="font-medium">Tier 1 picks the element</h3>
          <p className="mt-1 text-sm text-muted">Role, name, text, attributes and position, scored in milliseconds. A margin gate refuses close calls.</p>
          <ul className="mt-6 space-y-3">
            {bars.map((b) => (
              <li key={b.name} className="text-sm">
                <div className="mb-1 flex justify-between">
                  <span className={b.chosen ? "font-medium" : "text-muted"}>{b.name}</span>
                  <span className="font-mono text-xs text-dim">{b.chosen ? "chosen" : "runner-up"}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-chip-hover">
                  <div className={`h-full rounded-full ${b.chosen ? "accent-gradient" : "bg-line-strong"}`} style={{ width: `${String(b.score * 100)}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </Card>
        <Card as="article" className="md:col-span-5">
          <h3 className="font-medium">The verifier checks behaviour</h3>
          <p className="mt-1 text-sm text-muted">The candidate is clicked in a sandboxed copy. Its API calls must match the baseline.</p>
          <dl className="mt-6 space-y-2 font-mono text-xs">
            <div className="flex justify-between rounded-lg bg-chip px-3 py-2"><dt className="text-muted">expected</dt><dd>POST /api/cart</dd></div>
            <div className="flex justify-between rounded-lg bg-chip px-3 py-2"><dt className="text-muted">look-alike</dt><dd className="text-red-400">DELETE /api/orders/{"{id}"} ✗</dd></div>
            <div className="flex justify-between rounded-lg bg-chip px-3 py-2"><dt className="text-muted">true target</dt><dd className="text-accent">POST /api/cart ✓</dd></div>
          </dl>
        </Card>
        <Card as="article" className="md:col-span-5">
          <h3 className="font-medium">Fails closed</h3>
          <p className="mt-1 text-sm text-muted">No verified replacement? The original Playwright error is re-raised, unchanged. Green tests are never turned red.</p>
          <p className="mt-6 rounded-lg border border-line bg-chip px-3 py-2 font-mono text-xs text-muted">TimeoutError: locator("#add-to-cart") … (re-raised)</p>
        </Card>
        <Card as="article" className="md:col-span-7">
          <h3 className="font-medium">A patch, not magic</h3>
          <p className="mt-1 mb-5 text-sm text-muted">You review the diff, accept it, and apply it to the test file.</p>
          <TerminalCard title="patch.diff">
            <p className="text-zinc-400">@@ test_cart.py @@</p>
            <p className="text-red-400">-    page.click("#add-to-cart")</p>
            <p className="text-green-400">+    page.get_by_role("button", name="Add to basket").click()</p>
          </TerminalCard>
        </Card>
      </div>
    </section>
  );
}

const ARCH = [
  { t: "pytest plugin", d: "Wraps Playwright actions; re-raises the original error when it cannot prove a heal.", tag: "src/healwright/plugin" },
  { t: "Healing engine", d: "Tier 1 scorer, margin gate, Tier 2 vision client, sandbox verifier, live re-check.", tag: "engine · tier1 · tier2 · verify" },
  { t: "Artifacts", d: "Heal events as JSON lines, screenshots, candidates and patches. No database.", tag: ".healwright/runs" },
  { t: "API + this app", d: "FastAPI reads the same files; React shows runs, events, the benchmark and the demo.", tag: "/api/v1" },
  { t: "Chaos Store", d: "A test shop with 66 scripted UI mutations: the benchmark and demo target.", tag: "chaos_store" },
];

function Architecture() {
  return (
    <section aria-labelledby="arch" className="space-y-10">
      <SectionHeader id="arch" eyebrow="Architecture" title="Small parts," italic="plain files" />
      <ol className="space-y-3">
        {ARCH.map((a, i) => (
          <li key={a.t} className="flex flex-col gap-2 rounded-[40px] border border-line bg-surface/30 p-4 transition-colors hover:bg-surface sm:flex-row sm:items-center sm:gap-6 sm:rounded-full sm:px-6">
            <span className="font-serif text-2xl text-dim italic tabular-nums">{String(i + 1).padStart(2, "0")}</span>
            <span className="min-w-40 font-medium">{a.t}</span>
            <span className="flex-1 text-sm text-muted">{a.d}</span>
            <code className="rounded-full border border-line px-3 py-1 font-mono text-xs text-dim">{a.tag}</code>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Footer() {
  const reduce = useReducedMotion();
  const line = Array.from({ length: 10 }, () => "HEAL · VERIFY · PATCH · ").join("");
  return (
    <footer className="overflow-hidden border-t border-line pt-16 pb-10">
      <div aria-hidden="true" className="mb-14 flex whitespace-nowrap">
        <motion.p className={`font-serif text-5xl text-dim italic md:text-7xl ${reduce ? "" : "animate-marquee"}`}>
          {line}
          {line}
        </motion.p>
      </div>
      <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-[var(--gutter)] md:flex-row md:items-center">
        <div>
          <p className="text-2xl font-medium tracking-tight">
            See it heal a test <span className="font-serif italic">live</span>.
          </p>
          <p className="mt-1 text-sm text-muted">The demo runs offline from recorded model replies.</p>
        </div>
        <div className="flex gap-3">
          <ButtonLink to="/demo" icon={<SendIcon />}>
            Try the live demo
          </ButtonLink>
          <ButtonLink to="/runs" variant="secondary">
            Open dashboard
          </ButtonLink>
        </div>
      </div>
      <p className="mx-auto mt-12 max-w-6xl px-[var(--gutter)] text-xs text-dim">© HealWright</p>
    </footer>
  );
}

export function LandingPage() {
  useTitle(undefined, "HealWright repairs broken Playwright selectors and proves every fix before the test passes.");
  return (
    <div className="bg-bg text-ink">
      <Hero />
      <main id="main" className="mx-auto max-w-6xl space-y-28 px-[var(--gutter)] py-24">
        <Metrics />
        <HowItWorks />
        <Features />
        <Architecture />
      </main>
      <Footer />
    </div>
  );
}
