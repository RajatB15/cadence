import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { LoadingBlock, Shell } from "./components/Shell";
import { ActivitiesPage } from "./pages/Activities";
import { FoodPage } from "./pages/Food";
import { GoalsPage } from "./pages/Goals";
import { OverviewPage } from "./pages/Overview";
import { PlanPage } from "./pages/Plan";
import { ReviewPage } from "./pages/Review";
import { SettingsPage } from "./pages/Settings";
import { VaultPage } from "./pages/Vault";
import { useAppLifecycle } from "./lib/useAppLifecycle";

// ECharts is heavy; only chart pages pull it in.
const WeightPage = lazy(() => import("./pages/Weight").then((m) => ({ default: m.WeightPage })));
const MetricPage = lazy(() => import("./pages/Metric").then((m) => ({ default: m.MetricPage })));
const ActivityPage = lazy(() => import("./pages/ActivityDetail").then((m) => ({ default: m.ActivityPage })));
const CoachPage = lazy(() => import("./pages/Coach").then((m) => ({ default: m.CoachPage })));
const LabPage = lazy(() => import("./pages/Lab").then((m) => ({ default: m.LabPage })));
const ScorePage = lazy(() => import("./pages/Score").then((m) => ({ default: m.ScorePage })));

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
});

function Lifecycle() {
  useAppLifecycle();
  return null;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Lifecycle />
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<OverviewPage />} />
            <Route
              path="score"
              element={
                <Suspense fallback={<LoadingBlock height={640} />}>
                  <ScorePage />
                </Suspense>
              }
            />
            <Route
              path="coach"
              element={
                <Suspense fallback={<LoadingBlock height={640} />}>
                  <CoachPage />
                </Suspense>
              }
            />
            <Route
              path="weight"
              element={
                <Suspense fallback={<LoadingBlock height={520} />}>
                  <WeightPage />
                </Suspense>
              }
            />
            <Route path="plan" element={<PlanPage />} />
            <Route path="food" element={<FoodPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route
              path="lab"
              element={
                <Suspense fallback={<LoadingBlock height={640} />}>
                  <LabPage />
                </Suspense>
              }
            />
            <Route path="review" element={<ReviewPage />} />
            <Route path="activities" element={<ActivitiesPage />} />
            <Route
              path="activities/:id"
              element={
                <Suspense fallback={<LoadingBlock height={640} />}>
                  <ActivityPage />
                </Suspense>
              }
            />
            <Route path="vault" element={<VaultPage />} />
            <Route
              path="metrics/:metric"
              element={
                <Suspense fallback={<LoadingBlock height={520} />}>
                  <MetricPage />
                </Suspense>
              }
            />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<OverviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
