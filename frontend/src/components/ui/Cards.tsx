import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "figure";
}) {
  return <Tag className={`rounded-3xl border border-line bg-surface p-5 ${className}`}>{children}</Tag>;
}

export function SectionHeader({
  eyebrow,
  title,
  italic,
  children,
  id,
  as: H = "h2",
}: {
  eyebrow?: string;
  title: string;
  italic?: string;
  children?: ReactNode;
  id?: string;
  as?: "h1" | "h2";
}) {
  return (
    <header>
      {eyebrow ? (
        <p className="mb-3 flex items-center gap-3 text-xs tracking-[0.3em] text-muted uppercase">
          <span aria-hidden="true" className="h-px w-8 bg-line-strong" />
          {eyebrow}
        </p>
      ) : null}
      <H id={id} className={`${H === "h1" ? "text-3xl md:text-4xl" : "text-2xl md:text-3xl"} font-medium tracking-tight`}>
        {title} {italic ? <span className="font-serif font-normal italic">{italic}</span> : null}
      </H>
      {children ? <div className="mt-2 max-w-3xl text-sm text-muted">{children}</div> : null}
    </header>
  );
}

export function StatCard({ value, label, caption }: { value: string; label: string; caption?: string }) {
  return (
    <div className="group relative flex h-44 flex-col items-center justify-center overflow-hidden rounded-xl border border-line bg-surface text-ink shadow-md duration-500 hover:-translate-y-2">
      <svg
        viewBox="0 0 200 200"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        className="absolute z-10 h-40 w-40 fill-accent/30 blur duration-500 group-hover:scale-105 group-hover:blur-none"
      >
        <path
          transform="translate(100 100)"
          d="M39.5,-49.6C54.8,-43.2,73.2,-36.5,78.2,-24.6C83.2,-12.7,74.8,4.4,69,22.5C63.3,40.6,60.2,59.6,49.1,64.8C38.1,70,19,61.5,0.6,60.7C-17.9,59.9,-35.9,67,-47.2,61.9C-58.6,56.7,-63.4,39.5,-70,22.1C-76.6,4.7,-84.9,-12.8,-81.9,-28.1C-79,-43.3,-64.6,-56.3,-49.1,-62.5C-33.6,-68.8,-16.8,-68.3,-2.3,-65.1C12.1,-61.9,24.2,-55.9,39.5,-49.6Z"
        />
      </svg>
      <div className="z-20 flex flex-col items-center justify-center px-4 text-center">
        <span className="text-5xl font-bold tabular-nums">{value}</span>
        <p className="font-bold">{label}</p>
        {caption ? <p className="mt-1 text-xs text-muted">{caption}</p> : null}
      </div>
    </div>
  );
}

export function TerminalCard({
  title = "bash",
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`w-full rounded-lg bg-black p-6 font-mono text-white ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex space-x-2" aria-hidden="true">
          <div className="h-3 w-3 rounded-full bg-red-500" />
          <div className="h-3 w-3 rounded-full bg-yellow-500" />
          <div className="h-3 w-3 rounded-full bg-green-500" />
        </div>
        <div className="flex items-center gap-3">
          <p className="truncate text-sm text-zinc-300">{title}</p>
          {action}
        </div>
      </div>
      <div className="mt-4 text-sm">{children}</div>
    </div>
  );
}
