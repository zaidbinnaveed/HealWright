import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { ToastContext, type Kind, type ToastItem } from "./toast-context";

const ICON: Record<Kind, { path: string; color: string }> = {
  success: { path: "m4.5 12.75 6 6 9-13.5", color: "text-[#2b9875]" },
  error: { path: "M12 9v3.75m0 3.75h.008M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z", color: "text-red-400" },
  info: { path: "m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z", color: "text-sky-400" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const reduce = useReducedMotion();
  const dismiss = useCallback((id: number) => {
    setItems((all) => all.filter((t) => t.id !== id));
  }, []);
  const push = useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = next.current++;
      setItems((all) => [...all.slice(-3), { ...t, id }]);
      window.setTimeout(() => {
        dismiss(id);
      }, t.kind === "error" ? 8000 : 4500);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-72 flex-col gap-2 text-xs sm:w-80"
      >
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div
              key={t.id}
              role={t.kind === "error" ? "alert" : "status"}
              initial={reduce ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, x: 24 }}
              className="pointer-events-auto flex min-h-14 w-full cursor-default items-center justify-between rounded-lg bg-[#232531] px-[10px] py-2 shadow-lg"
            >
              <div className="flex gap-2">
                <div className={`${ICON[t.kind].color} h-fit rounded-lg bg-white/5 p-1 backdrop-blur-xl`}>
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="h-6 w-6" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d={ICON[t.kind].path} />
                  </svg>
                </div>
                <div>
                  <p className="text-white">{t.title}</p>
                  {t.description ? <p className="text-gray-400">{t.description}</p> : null}
                </div>
              </div>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() => {
                  dismiss(t.id);
                }}
                className="rounded-md p-1 text-gray-500 transition-colors ease-linear hover:bg-white/5"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="h-5 w-5" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
