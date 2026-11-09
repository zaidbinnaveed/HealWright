import { createContext, useContext } from "react";

export type Kind = "success" | "error" | "info";
export interface ToastItem {
  id: number;
  kind: Kind;
  title: string;
  description?: string;
}

export const ToastContext = createContext<(t: Omit<ToastItem, "id">) => void>(() => undefined);

/** Show a toast (see ToastProvider in ./Toast.tsx). */
export function useToast() {
  return useContext(ToastContext);
}
