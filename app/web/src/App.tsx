import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { lazy, Suspense, useEffect, useRef, type ComponentType, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { LoadingBlock, Shell } from "./components/Shell";
import { shouldRetry } from "./lib/api";
import { useAppLifecycle } from "./lib/useAppLifecycle";
import { OverviewPage } from "./pages/Overview";

// Only Home ships in the entry bundle; every other page (and ECharts/MapLibre with it) loads on demand.
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })));

const WeightPage = page(() => import("./pages/Weight"), "WeightPage");
const MetricPage = page(() => import("./pages/Metric"), "MetricPage");
const ActivityPage = page(() => import("./pages/ActivityDetail"), "ActivityPage");
const CoachPage = page(() => import("./pages/Coach"), "CoachPage");
const LabPage = page(() => import("./pages/Lab"), "LabPage");
const PhasesPage = page(() => import("./pages/Phases"), "PhasesPage");
const PhasePage = page(() => import("./pages/Phases"), "PhasePage");
const ScorePage = page(() => import("./pages/Score"), "ScorePage");
const ActivitiesPage = page(() => import("./pages/Activities"), "ActivitiesPage");
const EventsPage = page(() => import("./pages/Events"), "EventsPage");
const EventPage = page(() => import("./pages/Events"), "EventPage");
const FoodPage = page(() => import("./pages/Food"), "FoodPage");
const ReadingPage = page(() => import("./pages/Reading"), "ReadingPage");
const FoodCrawlPage = page(() => import("./pages/FoodCrawl"), "FoodCrawlPage");
const GoalsPage = page(() => import("./pages/Goals"), "GoalsPage");
const PlanPage = page(() => import("./pages/Plan"), "PlanPage");
const ReviewPage = page(() => import("./pages/Review"), "ReviewPage");
const SettingsPage = page(() => import("./pages/Settings"), "SettingsPage");
const VaultPage = page(() => import("./pages/Vault"), "VaultPage");

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: shouldRetry } },
});

function Lifecycle() {
  useAppLifecycle();
  return null;
}

// The page fades in over the spot its skeleton held once the chunk has loaded.
function Pending({ height, onShown }: { height: number; onShown: () => void }) {
  useEffect(onShown, [onShown]);
  return <LoadingBlock height={height} />;
}
function Gate({ children, height }: { children: ReactNode; height: number }) {
  const waited = useRef(false);
  const mark = useRef(() => { waited.current = true; }).current;
  // Only a page whose chunk actually had to load fades in; an already-loaded one just takes the route transition.
  return (
    <Suspense fallback={<Pending height={height} onShown={mark} />}>
      <div className={waited.current ? "fade-in" : undefined}>{children}</div>
    </Suspense>
  );
}
const wrap = (node: ReactNode, height = 520) => <Gate height={height}>{node}</Gate>;

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* "user": motion drops transform and layout animations when the system asks for reduced motion. */}
      <MotionConfig reducedMotion="user">
      <Lifecycle />
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<OverviewPage />} />
            <Route path="score" element={wrap(<ScorePage />, 640)} />
            <Route path="coach" element={wrap(<CoachPage />, 640)} />
            <Route path="weight" element={wrap(<WeightPage />)} />
            <Route path="plan" element={wrap(<PlanPage />, 640)} />
            <Route path="food" element={wrap(<FoodPage />, 640)} />
            <Route path="reading" element={wrap(<ReadingPage />)} />
            <Route path="food/library" element={wrap(<FoodCrawlPage />)} />
            <Route path="goals" element={wrap(<GoalsPage />)} />
            <Route path="lab" element={wrap(<LabPage />, 640)} />
            <Route path="review" element={wrap(<ReviewPage />)} />
            <Route path="activities" element={wrap(<ActivitiesPage />, 640)} />
            <Route path="phases" element={wrap(<PhasesPage />, 420)} />
            <Route path="phases/:id" element={wrap(<PhasePage />, 640)} />
            <Route path="events" element={wrap(<EventsPage />)} />
            <Route path="events/:id" element={wrap(<EventPage />)} />
            <Route path="activities/:id" element={wrap(<ActivityPage />, 640)} />
            <Route path="vault" element={wrap(<VaultPage />, 560)} />
            <Route path="metrics/:metric" element={wrap(<MetricPage />)} />
            <Route path="settings" element={wrap(<SettingsPage />, 640)} />
            <Route path="*" element={<OverviewPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  );
}
