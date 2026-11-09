import { useCallback, useEffect, useState } from "react";
import type { ApiErrorBody } from "./types";

export const API = "/api/v1";

/**
 * Showcase build (`vite build --mode showcase`, the hosted site): there is no backend, so
 * every read comes from a bundled snapshot of real data under /showcase/data/, laid out
 * like the API (`/runs/<id>` -> `/showcase/data/runs/<id>.json`). Writes are not offered.
 */
export const SHOWCASE = import.meta.env.MODE === "showcase";

function showcasePath(path: string): string {
  if (path.startsWith("/showcase/")) return path;
  const clean = path.split("?")[0] ?? path;
  return `/showcase/data${clean}${clean.endsWith(".json") ? "" : ".json"}`;
}

async function showcaseRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (init?.method && init.method !== "GET") {
    throw new ApiError(405, "READ_ONLY", "This action is available in a local HealWright install.", null);
  }
  let res: Response;
  try {
    res = await fetch(showcasePath(path), { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError(0, "NETWORK", "The page could not load its data. Check your connection and retry.", null);
  }
  if (!res.ok) throw new ApiError(res.status === 404 ? 404 : res.status, "NOT_FOUND", "Not found.", null);
  return (await res.json()) as T;
}

/** An error from the API envelope, or a network failure (code "NETWORK"). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
  ) {
    super(message);
  }
}

function isEnvelope(body: unknown): body is ApiErrorBody {
  return typeof body === "object" && body !== null && "error" in body;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (SHOWCASE) return showcaseRequest<T>(path, init);
  let res: Response;
  try {
    const headers = new Headers(init?.headers);
    headers.set("Accept", "application/json");
    res = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the HealWright API. Is the server running?", null);
  }
  const requestId = res.headers.get("X-Request-ID");
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    if (isEnvelope(body)) {
      throw new ApiError(res.status, body.error.code, body.error.message, body.error.request_id);
    }
    throw new ApiError(res.status, "HTTP_ERROR", `HTTP ${res.status}`, requestId);
  }
  return body as T;
}

export function postJson<T>(path: string, data: unknown, headers?: Record<string, string>) {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
    body: JSON.stringify(data),
  });
}

export interface Resource<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch `path` (null = skip) and expose loading / error / reload for the state components. */
export function useResource<T>(path: string | null): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    request<T>(path)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e), null));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  const reload = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  return { data, error, loading, reload };
}
