import { useState } from "react";
import { useTheme } from "../hooks/useTheme";
import { NavLink, Outlet } from "react-router";
import { ThemeToggle } from "./ui/Inputs";
import { ToastProvider } from "./ui/Toast";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 shrink-0 text-ink">
        <path d="M12 3 22 20H2z" fill="currentColor" />
        <path d="M8.5 15.2l2.4 2.3 4.6-5" fill="none" stroke="var(--bg)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {compact ? null : <span className="font-serif text-[22px] leading-none tracking-tight">HealWright</span>}
    </span>
  );
}

const ICONS = {
  runs: "M4 6h16M4 12h16M4 18h10",
  bench: "M5 20V10M12 20V4M19 20v-7",
  demo: "M6 4l13 8-13 8z",
  home: "M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6H9v6H4a1 1 0 01-1-1z",
  collapse: "M15 6l-6 6 6 6",
};

function Icon({ d }: { d: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

const NAV = [
  { to: "/runs", label: "Runs", icon: ICONS.runs },
  { to: "/benchmarks", label: "Benchmark", icon: ICONS.bench },
  { to: "/demo", label: "Live demo", icon: ICONS.demo },
];

function readCollapsed(): boolean {
  try {
    return localStorage.getItem("hw-sidebar") === "collapsed";
  } catch {
    return false;
  }
}

export function Layout() {
  const [dark, toggle] = useTheme();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const flip = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("hw-sidebar", next ? "collapsed" : "open");
    } catch {
      /* ignore */
    }
  };
  const link = (active: boolean) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
      active ? "bg-chip-hover font-medium text-ink" : "text-muted hover:bg-chip hover:text-ink"
    } ${collapsed ? "justify-center px-2" : ""}`;

  return (
    <ToastProvider>
      <div className="flex min-h-screen bg-bg">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
          Skip to content
        </a>
        <aside
          className={`shrink-0 self-stretch border-r border-line bg-bg-2 transition-[width] duration-300 ${collapsed ? "w-16" : "w-60"}`}
        >
          <div className="sticky top-0 flex h-screen flex-col">
          <div className={`flex h-16 items-center ${collapsed ? "justify-center" : "justify-between px-4"}`}>
            <NavLink to="/" aria-label="HealWright home">
              <Logo compact={collapsed} />
            </NavLink>
          </div>
          <nav aria-label="Main" className="flex-1 space-y-6 px-3 py-2">
            <div>
              {collapsed ? null : <p className="mb-2 px-3 text-[11px] tracking-[0.2em] text-dim uppercase">Workspace</p>}
              <ul className="space-y-1">
                {NAV.map((n) => (
                  <li key={n.to}>
                    <NavLink to={n.to} title={collapsed ? n.label : undefined} className={({ isActive }) => link(isActive)}>
                      <Icon d={n.icon} />
                      {collapsed ? <span className="sr-only">{n.label}</span> : n.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
          <div className={`flex items-center gap-2 border-t border-line p-3 ${collapsed ? "flex-col" : "justify-between"}`}>
            <NavLink to="/" title="Project site" className="rounded-lg p-2 text-muted hover:bg-chip hover:text-ink">
              <Icon d={ICONS.home} />
              <span className="sr-only">Project site</span>
            </NavLink>
            <ThemeToggle dark={dark} onToggle={toggle} />
            <button
              type="button"
              onClick={flip}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!collapsed}
              className="rounded-lg p-2 text-muted hover:bg-chip hover:text-ink"
            >
              <span className={`block transition-transform ${collapsed ? "rotate-180" : ""}`}>
                <Icon d={ICONS.collapse} />
              </span>
            </button>
          </div>
          </div>
        </aside>
        <main id="main" className="min-w-0 flex-1 px-6 py-8 lg:px-10">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </ToastProvider>
  );
}

export function SiteLayout() {
  return (
    <ToastProvider>
      <Outlet />
    </ToastProvider>
  );
}
