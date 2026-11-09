import { useState } from "react";

/** Light/dark theme on <html class="dark">, remembered in localStorage (best effort). */
export function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("hw-theme", next ? "dark" : "light");
    } catch {
      /* storage may be blocked; the toggle still works for this page */
    }
    setDark(next);
  };
  return [dark, toggle];
}
