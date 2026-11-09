import type { ReactNode } from "react";
import type { ApiError } from "../api/client";
import { Button } from "./ui/Button";
import { SkeletonCard as UvSkeletonCard, SkeletonRows } from "./ui/Feedback";

export function Skeleton({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return <SkeletonRows rows={Math.max(1, Math.round(lines / 2))} className={className} />;
}

export function SkeletonCard({ className = "" }: { className?: string }) {
  return <UvSkeletonCard className={className} />;
}

function StateBox({
  icon,
  title,
  children,
  action,
  tone = "neutral",
  role,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "error";
  role?: string;
}) {
  return (
    <div
      role={role}
      className={`flex flex-col items-center justify-center rounded-3xl border px-6 py-12 text-center ${
        tone === "error" ? "border-red-500/40 bg-red-500/5" : "border-line bg-surface"
      }`}
    >
      <div
        aria-hidden="true"
        className={`mb-4 flex size-14 items-center justify-center rounded-full ${tone === "error" ? "bg-red-500/10 text-red-500" : "bg-chip-hover text-muted"}`}
      >
        {icon}
      </div>
      <h2 className="text-base font-semibold">{title}</h2>
      {children ? <div className="mt-1.5 max-w-md text-sm text-muted">{children}</div> : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <StateBox
      title={title}
      action={action}
      icon={
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" strokeLinejoin="round" />
          <path d="M14 3v5h5M9 13h6M9 17h4" strokeLinecap="round" />
        </svg>
      }
    >
      {children}
    </StateBox>
  );
}

export function ErrorBanner({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const down = error.code === "NETWORK";
  return (
    <StateBox
      role="alert"
      tone="error"
      title={down ? "The HealWright API is not reachable" : `Error: ${error.code}`}
      action={
        onRetry ? (
          <Button variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
      icon={
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      }
    >
      <p>{error.message}</p>
      {error.requestId ? <p className="mt-1 font-mono text-xs opacity-75">request id {error.requestId}</p> : null}
    </StateBox>
  );
}
