import { useCallback, useEffect, useState } from "react";
import type { ApiErrorBody } from "./types";

export const API = "/api/v1";

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
