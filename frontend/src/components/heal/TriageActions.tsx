import { useId, useRef, useState } from "react";
import { ApiError, postJson } from "../../api/client";
import type { HealEvent } from "../../api/types";
import { TriageBadge } from "../StatusBadge";
import { Button } from "../ui/Button";
import { Card } from "../ui/Cards";
import { ConfirmDialog } from "../ui/Dialog";
import { useToast } from "../ui/toast-context";

type Pending = "accepted" | "rejected" | "apply" | null;

const COPY: Record<Exclude<Pending, null>, { title: string; body: string; cta: string }> = {
  accepted: {
    title: "Accept this heal?",
    body: "You confirm the new locator targets the right element. Nothing is written to your test file yet.",
    cta: "Accept",
  },
  rejected: {
    title: "Reject this heal?",
    body: "The patch will not be applied. The test stays red until someone fixes it by hand.",
    cta: "Reject",
  },
  apply: {
    title: "Apply the patch to the test file?",
    body: "HealWright re-checks the file's SHA-256 and runs git apply --check, then edits the file on disk.",
    cta: "Apply patch",
  },
};

export function TriageActions({ event, onChange }: { event: HealEvent; onChange: () => void }) {
  const [pending, setPending] = useState<Pending>(null);
  const [note, setNote] = useState(event.triage.note);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const idemKey = useRef<string>(crypto.randomUUID());
  const noteId = useId();
  const toast = useToast();
  const status = event.triage.status;
  const canPatch = Boolean(event.diff);
  const applied = status === "applied";
  const triageable = event.decision.status === "healed" || event.decision.status === "suggested";

  const open = (p: Exclude<Pending, null>) => {
    setPending(p);
    setMessage(null);
  };

  const confirm = async () => {
    if (pending === null) return;
    setBusy(true);
    try {
      let text: string;
      if (pending === "apply") {
        await postJson(`/heal-events/${event.id}/patch/apply`, {}, { "Idempotency-Key": idemKey.current });
        text = "Patch applied to the test file.";
      } else {
        await postJson(`/heal-events/${event.id}/triage`, { decision: pending, note });
        text = pending === "accepted" ? "Heal accepted." : "Heal rejected.";
      }
      setMessage({ ok: true, text });
      toast({ kind: "success", title: text });
      setPending(null);
      onChange();
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      const text = err ? `${err.code}: ${err.message}` : String(e);
      setMessage({ ok: false, text });
      toast({ kind: "error", title: "Triage failed", description: text });
      setPending(null);
    } finally {
      setBusy(false);
    }
  };

  const copy = pending ? COPY[pending] : null;
  return (
    <Card as="section" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 id="triage-title" className="text-sm font-semibold">Triage</h2>
        <TriageBadge status={status} />
      </div>
      {!triageable ? (
        <p className="text-sm text-muted">
          Nothing to accept: HealWright found no verified replacement, so the test stays red. Fix the test or the app by hand.
        </p>
      ) : (
        <>
          <div>
            <label htmlFor={noteId} className="block text-xs font-medium text-muted">
              Note (optional)
            </label>
            <textarea
              id={noteId}
              value={note}
              maxLength={1000}
              disabled={applied}
              onChange={(e) => { setNote(e.target.value); }}
              rows={2}
              className="mt-1 w-full rounded-lg border border-line bg-chip px-3 py-2 text-sm text-ink placeholder:text-dim focus:border-line-strong"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={applied || busy || status === "rejected"}
              onClick={() => { open("accepted"); }}
              title={status === "rejected" ? "Already rejected (a triage decision is final)" : undefined}
            >
              Accept
            </Button>
            <Button
              variant="secondary"
              disabled={applied || busy || status === "accepted"}
              onClick={() => { open("rejected"); }}
              title={status === "accepted" ? "Already accepted (a triage decision is final)" : undefined}
            >
              Reject
            </Button>
            <Button
              variant="secondary"
              className="ring-gradient"
              disabled={!canPatch || status !== "accepted" || busy}
              onClick={() => { open("apply"); }}
              title={!canPatch ? "No patch for this event" : status !== "accepted" ? "Accept the heal first" : undefined}
            >
              Apply patch
            </Button>
          </div>
        </>
      )}
      {message ? (
        <p role="status" className={`text-sm ${message.ok ? "text-accent-ink" : "text-red-500"}`}>
          {message.text}
        </p>
      ) : null}
      <ConfirmDialog
        open={copy !== null}
        title={copy?.title ?? ""}
        confirmLabel={copy?.cta ?? ""}
        tone={pending === "rejected" ? "danger" : "default"}
        busy={busy}
        onConfirm={() => { void confirm(); }}
        onClose={() => { setPending(null); }}
      >
        {copy?.body}
      </ConfirmDialog>
    </Card>
  );
}
