import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout, SiteLayout } from "./components/Layout";
import { EmptyState } from "./components/States";
import "./index.css";
import { HealEventPage } from "./pages/HealEventPage";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { DemoPage } from "./pages/DemoPage";
import { LandingPage } from "./pages/LandingPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { ShowcaseDemoPage } from "./pages/ShowcaseDemoPage";
import { SHOWCASE } from "./api/client";

const router = createBrowserRouter([
  { element: <SiteLayout />, children: [{ path: "/", element: <LandingPage /> }] },
  {
    element: <Layout />,
    children: [
      { path: "/runs", element: <RunsPage /> },
      { path: "/runs/:runId", element: <RunDetailPage /> },
      { path: "/events/:eventId", element: <HealEventPage /> },
      { path: "/benchmarks", element: <BenchmarkPage /> },
      { path: "/demo", element: SHOWCASE ? <ShowcaseDemoPage /> : <DemoPage /> },
      { path: "*", element: <EmptyState title="Page not found">There is no page at this address.</EmptyState> },
    ],
  },
]);

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  );
}
