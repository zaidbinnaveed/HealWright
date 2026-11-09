import type { ReactNode } from "react";

export function Spinner({ size = 20, label = "Loading" }: { size?: number; label?: string }) {
  return (
    <span role="status" aria-label={label} className="inline-flex">
      <span
        className="uv-spinner"
        style={{ ["--size-of-spinner" as string]: `${String(size)}px`, ["--spinner-border-width" as string]: `${String(Math.max(2, size / 12))}px` }}
      />
    </span>
  );
}

export function SkeletonRows({ rows = 4, className = "" }: { rows?: number; className?: string }) {
  return (
    <div role="status" aria-label="Loading" className={`space-y-1 ${className}`}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="relative flex w-full animate-pulse gap-2 p-4">
          <div className="h-12 w-12 rounded-full bg-ink/10" />
          <div className="flex-1">
            <div className="mb-1 h-5 w-3/5 rounded-lg bg-ink/10" />
            <div className="h-5 w-[90%] rounded-lg bg-ink/10" />
          </div>
          <div className="absolute bottom-5 right-0 h-4 w-4 rounded-full bg-ink/10" />
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div role="status" aria-label="Loading" className={`uv-skel-card ${className}`}>
      <div className="uv-skel-header">
        <div className="uv-skel-img" />
        <div className="uv-skel-details">
          <span className="uv-skel-name" />
          <span className="uv-skel-about" />
        </div>
      </div>
      <div className="uv-skel-description">
        <div className="uv-skel-line uv-skel-line-1" />
        <div className="uv-skel-line uv-skel-line-2" />
        <div className="uv-skel-line uv-skel-line-3" />
      </div>
      <div className="uv-skel-btns">
        <div className="uv-skel-btn uv-skel-btn-1" />
        <div className="uv-skel-btn uv-skel-btn-2" />
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="group/tt relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute -top-2 left-1/2 z-50 flex -translate-x-1/2 -translate-y-full flex-col items-center text-center text-xs opacity-0 transition-opacity group-focus-within/tt:visible group-focus-within/tt:opacity-100 group-hover/tt:visible group-hover/tt:opacity-100"
      >
        <span className="rounded-sm bg-ink px-2 py-1 whitespace-nowrap text-bg">{text}</span>
        <span className="h-0 w-fit border-x-8 border-t-8 border-x-transparent border-t-ink" />
      </span>
    </span>
  );
}

export function Checkbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="uv-checkbox text-sm text-muted">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => {
          onChange(e.target.checked);
        }}
      />
      <span>{children}</span>
    </label>
  );
}
