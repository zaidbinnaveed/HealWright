import { useEffect, useState } from "react";
import { request, SHOWCASE } from "../api/client";

/** What this deployment offers (GET /api/v1/features). A public demo hides review, apply
 * and watch mode; the static showcase has no backend at all. */
export interface Features {
  public: boolean;
  triage: boolean;
  apply: boolean;
  watch: boolean;
  demo_cooldown_s: number;
}

const LOCAL: Features = { public: false, triage: true, apply: true, watch: true, demo_cooldown_s: 0 };
const READ_ONLY: Features = { public: true, triage: false, apply: false, watch: false, demo_cooldown_s: 0 };
let cached: Promise<Features> | null = null;

function load(): Promise<Features> {
  if (SHOWCASE) return Promise.resolve(READ_ONLY);
  cached ??= request<Features>("/features").catch(() => LOCAL);
  return cached;
}

export function useFeatures(): Features | null {
  const [features, setFeatures] = useState<Features | null>(null);
  useEffect(() => {
    let live = true;
    void load().then((f) => {
      if (live) setFeatures(f);
    });
    return () => {
      live = false;
    };
  }, []);
  return features;
}
