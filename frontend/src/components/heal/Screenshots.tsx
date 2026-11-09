import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import type { HealEvent } from "../../api/types";
import { EmptyState } from "../States";
import { Card } from "../ui/Cards";
import { DotTabs } from "../ui/Navigation";

type Shot = "before" | "som";
const LABEL: Record<Shot, string> = { before: "Before (page at failure)", som: "Set-of-Mark (what the VLM saw)" };

export function Screenshots({ event }: { event: HealEvent }) {
  const available = (["before", "som"] as const).filter((k) => event.artifact_urls[k]);
  const [shot, setShot] = useState<Shot | null>(available[0] ?? null);
  const reduce = useReducedMotion();
  if (shot === null) {
    return <EmptyState title="No screenshots">The heal stopped before a screenshot was taken.</EmptyState>;
  }
  const url = event.artifact_urls[shot];
  return (
    <Card as="section" className="overflow-hidden p-0!">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <h2 id="shots-title" className="text-sm font-semibold">Screenshots</h2>
        <DotTabs<Shot> label="Screenshot" value={shot} onChange={setShot} tabs={available.map((k) => ({ value: k, label: LABEL[k] }))} />
      </div>
      <div className="relative aspect-[16/10] overflow-hidden bg-bg">
        <AnimatePresence mode="wait" initial={false}>
          <motion.img
            key={shot}
            src={url}
            alt={LABEL[shot]}
            className="absolute inset-0 h-full w-full object-contain"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduce ? { opacity: 1 } : { opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
        </AnimatePresence>
      </div>
    </Card>
  );
}
