import { useEffect } from "react";

const BASE = "HealWright";

/** Page title: "<page> · HealWright", or the home title when no page is given. */
export function useTitle(page?: string, description?: string) {
  useEffect(() => {
    document.title = page ? `${page} · ${BASE}` : `${BASE}: self-healing tests that never lie`;
    if (description) document.querySelector('meta[name="description"]')?.setAttribute("content", description);
  }, [page, description]);
}
