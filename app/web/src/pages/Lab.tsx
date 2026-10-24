import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Bike, ChevronDown, Footprints, Info } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { NoteGrid } from "../components/CoachNotes";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { clockTime as hms, signed } from "../lib/goals";
import type { AccuracyPoint, AccuracyStats, Headline, LabAccuracy, LabModel, LabRoutes, LabWhatIf, RouteView, WhatIfBundle, WhatIfPoint, WhatIfResult } from "../lib/types";

type Tab = "accuracy" | "model" | "routes" | "whatif";
const TABS: { value: Tab; label: string }[] = [
  { value: "accuracy", label: "Predictions" },
  { value: "model", label: "Fitness model" },
  { value: "routes", label: "Routes" },
  { value: "whatif", label: "What-ifs" },
];
const INTRO: Record<Tab, string> = {
  accuracy: "Cadence predicts how hard each planned session will be. Here is how often it was right.",
  model: "Does your body build and shed fitness at the textbook speed, or at its own? Tested on your data.",
  routes: "Runs and rides you have repeated, compared by effort rather than raw pace. Each session page shows its own route too.",
  whatif: "Replay recent weeks with one session changed to see what an easier day would have bought.",
};

const mmss = (s: number) => {
  const r = Math.round(s);
  return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
};
const TONE = { good: "#c8f560", info: "#6cc7ff", warn: "#ffbe55" } as const;

export function LabPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = TABS.some((t) => t.value === raw) ? (raw as Tab) : "accuracy";
  return (
    <>
      <PageHeader eyebrow="How far to trust it" title={<>The <em className="text-gold">lab.</em></>}>
        <Segmented label="Lab section" options={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      </PageHeader>
      <p className="-mt-6 mb-8 max-w-2xl text-sm text-mute">{INTRO[tab]}</p>
      {tab === "accuracy" && <AccuracyTab />}
      {tab === "model" && <ModelTab />}
      {tab === "routes" && <RoutesTab />}
      {tab === "whatif" && <WhatIfTab />}
    </>
  );
}

// ---- shared bits --------------------------------------------------------------------

function Panel({ title, eyebrow, aside, children }: { title: string; eyebrow?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="surface p-5 sm:p-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
          <h2 className="font-display text-3xl text-cream">{title}</h2>
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

function HeadlineBox({ h }: { h: Headline }) {
  return (
    <section className="surface flex items-start gap-4 p-5 sm:p-6" style={{ borderLeft: `3px solid ${TONE[h.tone]}` }}>
      <Info size={18} className="mt-0.5 shrink-0" style={{ color: TONE[h.tone] }} />
      <p className="text-paper">{h.text}</p>
    </section>
  );
}

function Explain({ items, title = "In plain words" }: { items: { q: string; a: string }[] | undefined; title?: string }) {
  if (!items?.length) return null;
  return (
    <section className="surface p-5 sm:p-8">
      <h2 className="mb-5 font-display text-3xl text-cream">{title}</h2>
      <dl className="grid gap-x-10 gap-y-5 lg:grid-cols-2">
        {items.map((x) => (
          <div key={x.q}>
            <dt className="eyebrow mb-1.5 !text-gold">{x.q}</dt>
            <dd className="text-sm leading-relaxed text-paper">{x.a}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Stat({ label, value, hint, color }: { label: string; value: ReactNode; hint?: ReactNode; color?: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-3xl" style={{ color: color ?? "#f2e8cf" }}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-dim">{hint}</p>}
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="surface p-10 text-center text-mute">{children}</div>;
}

function Query<T>({ q, children }: { q: { isPending: boolean; isError: boolean; error: unknown; data: T | undefined; refetch: () => unknown }; children: (d: T) => ReactNode }) {
  if (q.isPending) return <LoadingBlock height={420} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  return <>{children(q.data as T)}</>;
}

const Foot = ({ children }: { children: ReactNode }) => <p className="mt-5 max-w-3xl text-xs leading-relaxed text-dim">{children}</p>;

// ---- accuracy -----------------------------------------------------------------------

function AccuracyTab() {
  const q = useQuery({ queryKey: ["lab", "accuracy"], queryFn: api.labAccuracy });
  return (
    <Query q={q}>
      {(d: LabAccuracy) =>
        !d.has_data ? (
          <Empty>Sync some training to see how the predictions score.</Empty>
        ) : (
          <div className="space-y-6">
            <HeadlineBox h={d.headline} />
            <Explain items={d.explain} />
            <div className="grid gap-6 lg:grid-cols-2">
              <Panel title="Your planned sessions" eyebrow="Real test: predicted when you chose it, scored after">
                <Scores s={d.plans.overall} minBias={d.min_bias_n} empty="Plan a session on the Plan page and do it; it appears here once matched." />
                {d.plans.followed && (
                  <p className="mt-4 text-sm text-mute">
                    {d.plans.followed.done} of {d.plans.followed.of} past plans done{d.plans.followed.missed ? `, ${d.plans.followed.missed} missed` : ""}.
                  </p>
                )}
              </Panel>
              <Panel title="Walk-forward test" eyebrow="Instant check: each past session predicted from the ones before it">
                <Scores s={d.backtest} minBias={d.min_bias_n} empty="Needs 5+ sessions with heart-rate zones." />
                {d.backtest.window && <p className="mt-4 text-xs text-dim">{formatDate(d.backtest.window[0])} to {formatDate(d.backtest.window[1])}, given each session's duration and time in zones.</p>}
              </Panel>
            </div>
            <Panel title="Predicted against what happened" eyebrow="Dashed line = a perfect prediction · above it the session cost more than predicted">
              <Scatter plans={d.plans.points} backtest={d.backtest.points ?? []} />
            </Panel>
            <div className="grid gap-6 lg:grid-cols-2">
              <Panel title="Does Cadence correct itself?" eyebrow="Only when it is clearly off">
                {Object.keys(d.calibration).length ? (
                  <ul className="space-y-3 text-sm">
                    {Object.entries(d.calibration).map(([sport, c]) => (
                      <li key={sport} className="flex items-baseline justify-between gap-4 border-b border-line/60 pb-2">
                        <span className={clsx("text-paper", sport !== "all" && "capitalize")}>{sport === "all" ? "All sports" : sport}</span>
                        <span className="num text-gold">×{c.factor.toFixed(2)} <span className="text-xs text-dim">n={c.n}, raw {c.ratio_ci[0].toFixed(2)}–{c.ratio_ci[1].toFixed(2)}</span></span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-mute">
                    Not at the moment. Predictions are only nudged once they have been consistently high or low across {d.min_bias_n}+ sessions, so one odd week never changes anything.
                  </p>
                )}
                <Foot>The nudge is deliberately timid (it moves only part of the way and never more than 30–40%). Corrected predictions say so on the Plan page, and this page always scores the original, uncorrected number.</Foot>
              </Panel>
              <Panel title="Latest sessions" eyebrow="Predicted → actual load">
                {d.plans.recent.length ? (
                  <ul className="text-sm">
                    {d.plans.recent.map((r) => (
                      <li key={r.id} className="flex items-baseline justify-between gap-3 border-b border-line/60 py-2">
                        <span className="min-w-0 truncate text-paper">{r.title} <span className="text-xs text-dim">{formatDate(r.day)}</span></span>
                        <span className="num shrink-0 text-xs text-mute">{Math.round(r.predicted)} → {Math.round(r.actual)} <span className={Math.abs(r.error_pct) > 25 ? "text-amber" : "text-lime"}>{signed(r.error_pct, 0)}%</span></span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-mute">No matched sessions yet.</p>
                )}
                {d.form && <p className="mt-4 text-xs text-dim">Tomorrow-morning form was typically {d.form.typical_abs_error} points off the prediction (across {d.form.n} sessions); anything unplanned that day adds to that.</p>}
              </Panel>
            </div>
          </div>
        )
      }
    </Query>
  );
}

function Scores({ s, minBias, empty }: { s: AccuracyStats; minBias: number; empty: string }) {
  if (!s.enough) return <p className="text-sm text-mute">{s.n} so far. {empty}</p>;
  return (
    <>
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-3">
        <Stat label="Typical miss" value={`${s.typical_error_pct}%`} hint={`across ${s.n} sessions`} />
        <Stat label="Close calls" value={`${s.within_25_pct}%`} hint={`within 25% of prediction (${s.within_10_pct}% within 10%)`} color="#6cc7ff" />
        <Stat
          label="Leans" value={s.biased ? `${signed(s.bias_pct!, 0)}%` : "no"} color={s.biased ? "#ffbe55" : "#c8f560"}
          hint={s.n < minBias ? `too early to say (needs ${minBias}+)` : s.biased ? `sessions cost ${signed(s.bias_pct!, 0)}% vs predicted` : "no consistent over- or under-prediction"}
        />
      </div>
      {s.range_coverage_pct != null && <p className="mt-4 text-xs text-dim">The low–high range shown on the Plan page contained the real load {s.range_coverage_pct}% of the time.</p>}
    </>
  );
}

function Scatter({ plans, backtest }: { plans: AccuracyPoint[]; backtest: AccuracyPoint[] }) {
  const max = Math.max(50, ...plans.map((p) => Math.max(p.predicted, p.actual)), ...backtest.map((p) => Math.max(p.predicted, p.actual)));
  const option = useMemo<ChartOption>(() => {
    const dot = (rows: AccuracyPoint[]) => rows.map((p) => [Math.round(p.predicted), Math.round(p.actual), p.sport, p.day]);
    return {
      ...chartBase,
      grid: { ...chartBase.grid, bottom: 40 },
      tooltip: { ...chartBase.tooltip, trigger: "item", formatter: (q: { data: [number, number, string, string] }) => `${q.data[2]} · ${formatDate(q.data[3])}<br/>predicted <b>${q.data[0]}</b> · actual <b>${q.data[1]}</b>` },
      xAxis: { ...chartBase.xAxis, type: "value", min: 0, max: Math.ceil(max / 10) * 10, name: "Predicted load", nameLocation: "middle", nameGap: 28, nameTextStyle: { color: "#5c5a55", fontSize: 11 } },
      yAxis: { ...chartBase.yAxis, scale: false, min: 0, max: Math.ceil(max / 10) * 10, name: "Actual", nameTextStyle: { color: "#5c5a55", fontSize: 11 } },
      legend: { show: false },
      series: [
        { name: "Exactly right", type: "line", symbol: "none", silent: true, lineStyle: { color: "#5c5a55", type: "dashed", width: 1 }, data: [[0, 0], [max, max]] },
        { name: "Walk-forward", type: "scatter", symbolSize: 7, itemStyle: { color: "rgba(108,199,255,0.55)" }, data: dot(backtest) },
        { name: "Your plans", type: "scatter", symbolSize: 11, itemStyle: { color: "#d9b26a" }, data: dot(plans) },
      ],
    };
  }, [plans, backtest, max]);
  if (!plans.length && !backtest.length) return <p className="py-10 text-center text-sm text-dim">Nothing to plot yet.</p>;
  return (
    <>
      <Chart option={option} height={340} label="Predicted against actual training load" />
      <p className="mt-3 flex flex-wrap gap-5 text-xs text-mute">
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-gold" />Your plans</span>
        <span><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-sky/70" />Walk-forward test</span>
      </p>
    </>
  );
}

// ---- fitness model ----------------------------------------------------------------------

function ModelTab() {
  const q = useQuery({ queryKey: ["lab", "model"], queryFn: api.labModel });
  return (
    <Query q={q}>
      {(d: LabModel) =>
        !d.has_data ? (
          <Empty>Sync some training to fit your fitness model.</Empty>
        ) : (
          <div className="space-y-6">
            <HeadlineBox h={d.headline} />
            <Explain items={d.explain} />
            {!d.valid ? (
              <Panel title="Not enough data yet" eyebrow="Needs more weeks first">
                <p className="text-sm text-mute">Needs {d.missing}.</p>
                <Foot>With fewer weeks the maths would fit random wobble and look convincing while being wrong, so it waits.</Foot>
              </Panel>
            ) : (
              <ModelBody d={d as Extract<LabModel, { valid: true }>} />
            )}
          </div>
        )
      }
    </Query>
  );
}

function ModelBody({ d }: { d: Extract<LabModel, { has_data: true }> & { valid: true } }) {
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [
        { name: "Modelled", type: "line", symbol: "none", lineStyle: { color: "#d9b26a", width: 2 }, data: (d.curve ?? []).map((p) => [p.day, p.value]) },
        { name: "Observed (weekly median)", type: "scatter", symbolSize: 8, itemStyle: { color: "#6cc7ff" }, data: (d.series ?? []).map((p) => [p.day, p.observed]) },
      ],
    }),
    [d.curve, d.series],
  );
  const r = d.region!;
  const cv = d.cv!;
  return (
    <>
      <Panel
        title="Your numbers" eyebrow={d.adopted ? "Used for what-ifs and the rest estimate" : "Not used: the standard 42/7 days stay"}
        aside={<span className={clsx("chip", d.adopted ? "!border-lime/40 !text-lime" : "")}>{d.adopted ? "Adopted" : "Standard kept"}</span>}
      >
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat label="Fitness builds over" value={`${d.tau1} days`} hint={`textbook ${d.default_taus![0]} · data allow ${r.tau1[0]}–${r.tau1[1]}`} color="#6cc7ff" />
          <Stat label="Fatigue fades in" value={`${d.tau2} days`} hint={`textbook ${d.default_taus![1]} · data allow ${r.tau2[0]}–${r.tau2[1]}`} color="#ff6a55" />
          <Stat label="Weeks used" value={d.n} hint={`over ${d.span_days} days`} />
          <Stat label="Follows past weeks" value={d.r2 != null ? `${Math.round(d.r2 * 100)}%` : "—"} hint="looks flattering; the test below is what counts" />
        </div>
        {!d.adopted && d.why_not && <p className="mt-5 text-sm text-mute">Why: {d.why_not}.</p>}
      </Panel>
      <Panel title="The honesty test" eyebrow="Predict weeks the model never saw (average miss, lower is better)">
        <div className="grid grid-cols-3 gap-6">
          <Stat label="Your fit" value={cv.personal.toFixed(2)} hint="average miss on unseen weeks" color={d.adopted ? "#c8f560" : undefined} />
          <Stat label="Textbook 42/7" value={cv.default.toFixed(2)} hint={cv.gain_vs_default_pct >= 0 ? `your fit is ${Math.round(cv.gain_vs_default_pct)}% closer` : `your fit is ${Math.round(-cv.gain_vs_default_pct)}% further off`} />
          <Stat label="Just guess the average" value={cv.mean.toFixed(2)} hint="the lazy baseline" />
        </div>
        <Foot>Your numbers are only used when they beat both the textbook numbers and the plain average by at least 5% on weeks they never saw. The "data allow" ranges show how much the data cannot tell apart: wide means unsure.</Foot>
      </Panel>
      <Panel title="Your efficiency, and what the model expected" eyebrow={`${d.performance_label}: dots are real weeks, the line is the model`}>
        <Chart option={option} height={320} label="Observed and modelled aerobic efficiency" />
        {d.taper && (
          <p className="mt-5 text-sm text-mute">
            {d.taper.peak_day === 0
              ? "If you stopped training now, this model has no further gain to offer."
              : <>If you stopped now, the model peaks after about <span className="num text-paper">{d.taper.peak_day}</span> days
                (anywhere from {d.taper.range[0]} to {d.taper.range[1]} across the constants the data cannot rule out){d.taper.gain_pct != null && <>, roughly {signed(d.taper.gain_pct)}% above today</>}. How the model behaves, not a taper plan.</>}
          </p>
        )}
        <Foot>"Efficiency" is how fast you run per heartbeat above your resting rate, taken as a weekly median: a proxy for fitness, not a race result. Models like this are fragile with little data (Hellard et al. 2006), which is why the unseen-weeks test decides.</Foot>
      </Panel>
    </>
  );
}

// ---- routes ------------------------------------------------------------------------------

function RoutesTab() {
  const q = useQuery({ queryKey: ["lab", "routes"], queryFn: api.labRoutes });
  return (
    <Query q={q}>
      {(d: LabRoutes) =>
        !d.has_data ? (
          <Empty>Sync some training to find repeated routes.</Empty>
        ) : !d.routes.length ? (
          <Empty>
            <p className="text-paper">{d.reason}</p>
            <p className="mt-2 text-sm">{d.n_with_gps} outdoor sessions have GPS start coordinates. Routes match on start and end points, bounding box, length and climb, so they need Garmin activity data rather than demo data.</p>
          </Empty>
        ) : (
          <div className="space-y-4">
            {d.routes.map((r, i) => <RouteCard key={r.id} r={r} open={i === 0} />)}
            <Foot>Routes are matched from the activity summary (start/end, bounding box, distance within 7%, climb), not a map match, so two different loops with the same start and length could merge. Weather is context only and is not used to adjust pace.</Foot>
          </div>
        )
      }
    </Query>
  );
}

function RouteCard({ r, open: initial }: { r: RouteView; open: boolean }) {
  const [open, setOpen] = useState(initial);
  const Icon = r.sport === "ride" ? Bike : Footprints;
  const v = r.latest.vs_prior;
  return (
    <section className="surface">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex w-full items-center gap-4 p-5 text-left sm:p-6">
        <Icon size={20} className="shrink-0 text-gold" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-2xl text-cream">{r.name}</h3>
          <p className="text-xs text-mute">{r.n} efforts · {r.distance_km} km{r.elevation_m != null ? ` · ${r.elevation_m} m up` : ""}{r.loop ? " · loop" : ""} · {formatDate(r.first)} to {formatDate(r.last)}</p>
        </div>
        <div className="hidden text-right sm:block">
          <p className="num text-lg text-cream">{hms(r.latest.time_s)}</p>
          <p className={clsx("num text-xs", v.time_s <= 0 ? "text-lime" : "text-amber")}>{v.time_s <= 0 ? "−" : "+"}{mmss(Math.abs(v.time_s))} vs usual</p>
        </div>
        <ChevronDown size={18} className={clsx("shrink-0 text-mute transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-6 border-t border-line p-5 sm:p-6">
          {r.notes.length > 0 && <NoteGrid notes={r.notes} compact />}
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <Stat label="Best" value={hms(r.best.time_s)} hint={formatDate(r.best.day)} color="#c8f560" />
            <Stat label="Median" value={hms(r.median_time_s)} hint={`${r.n} efforts`} />
            <Stat label="Latest HR" value={r.latest.avg_hr ?? "—"} hint={v.avg_hr != null ? `${signed(v.avg_hr)} bpm vs usual` : undefined} color="#ff6a55" />
            <Stat label="Efficiency" value={v.ef_pct != null ? `${signed(v.ef_pct)}%` : "—"} hint={r.trend ? `trend ${signed(r.trend.change_pct)}% (${signed(r.trend.ci_pct[0])} to ${signed(r.trend.ci_pct[1])})` : "needs 5+ runs over 4+ weeks"} color="#6cc7ff" />
          </div>
          <RouteChart r={r} />
          <EffortTable r={r} />
        </div>
      )}
    </section>
  );
}

function RouteChart({ r }: { r: RouteView }) {
  const hasEf = r.efforts.some((e) => e.ef != null);
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (v: number) => String(v) },
      yAxis: [
        { ...chartBase.yAxis, inverse: true, axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => hms(v) } },
        ...(hasEf ? [{ ...chartBase.yAxis, position: "right", splitLine: { show: false }, axisLabel: { color: "#5c5a55", fontSize: 10 } }] : []),
      ],
      series: [
        { name: "Time", type: "line", data: r.efforts.map((e) => [e.day, e.time_s]), symbol: "circle", symbolSize: 7, lineStyle: { color: "#d9b26a", width: 2 }, itemStyle: { color: "#d9b26a" } },
        ...(hasEf ? [{ name: "Efficiency", type: "line", yAxisIndex: 1, data: r.efforts.filter((e) => e.ef != null).map((e) => [e.day, e.ef]), symbol: "none", lineStyle: { color: "#6cc7ff", width: 1.5, type: "dashed" } }] : []),
      ],
    }),
    [r.efforts, hasEf],
  );
  return <Chart option={option} height={240} label={`${r.name}: time and efficiency per effort`} />;
}

function EffortTable({ r }: { r: RouteView }) {
  const rows = [...r.efforts].reverse().slice(0, 12);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="eyebrow text-left"><th className="py-2 font-semibold">Date</th><th className="font-semibold">Time</th><th className="font-semibold">Avg HR</th><th className="font-semibold">Efficiency</th><th className="font-semibold">Conditions</th></tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id} className="border-t border-line/60">
              <td className="py-2"><Link to={`/activities/${e.id}`} className="text-paper hover:text-gold">{formatDate(e.day)}</Link></td>
              <td className="num">{hms(e.time_s)}{e.id === r.best.id && <span className="ml-2 text-xs text-lime">best</span>}{e.hard && <span className="ml-2 text-xs text-amber">hard</span>}</td>
              <td className="num text-mute">{e.avg_hr ?? "—"}</td>
              <td className="num text-mute">{e.ef != null ? e.ef.toFixed(3) : "—"}</td>
              <td className="num text-xs text-mute">{e.temperature != null ? `${Math.round(e.temperature)}°C` : "—"}{e.wind != null ? ` · ${Math.round(e.wind)} km/h` : ""}{e.hot ? " · hot" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- what-ifs -----------------------------------------------------------------------------

const ACTION_LABEL = { skip: "Skip it", easy: "Same time, kept easy", half: "Cut in half" } as const;

function WhatIfTab() {
  const q = useQuery({ queryKey: ["lab", "whatif"], queryFn: api.labWhatIf });
  return (
    <Query q={q}>
      {(d: LabWhatIf) =>
        !d.has_data ? (
          <Empty>Sync some training to replay it.</Empty>
        ) : (
          <div className="space-y-6">
            {Object.entries(d.bundles).map(([k, b]) => <Bundle key={k} b={b} />)}
            {!Object.keys(d.bundles).length && (
              <Empty>
                <p className="text-paper">No pattern to replay.</p>
                <p className="mt-2 text-sm">No grey-zone sessions or back-to-back hard days in the last {d.window_days / 7} weeks, or fewer than two of them. You can still replay any single session below.</p>
              </Empty>
            )}
            {d.items.length > 0 && (
              <Panel title="Session by session" eyebrow="Each kept easy at the same duration">
                <ul className="text-sm">
                  {d.items.map((i) => (
                    <li key={i.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line/60 py-2.5">
                      <Link to={`/activities/${i.id}`} className="min-w-0 truncate text-paper hover:text-gold">
                        {i.name} <span className="text-xs text-dim">{formatDate(i.day)} · {i.kind === "grey" ? "grey zone" : "hard again"}</span>
                      </Link>
                      <span className="num text-xs text-mute">
                        load {i.load} → {i.load_after}{i.rough ? " (rough)" : ""} · fitness <span className="text-sky">{signed(i.fitness_delta)}</span>
                        {i.next_morning_form != null && <> · next morning form <span className="text-lime">{signed(i.next_morning_form)}</span></>}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
            <Custom d={d} />
            <Foot>The replay changes only the training-load inputs and reruns the same 42/7-day fitness/fatigue model and acute:chronic ratio used elsewhere in Cadence. Sleep, illness and stress are not in it, and later choices (training harder the next day) are not modelled. "Kept easy" uses your own median load per minute on easy sessions of that sport, and the changed load never exceeds the original.</Foot>
          </div>
        )
      }
    </Query>
  );
}

function Bundle({ b }: { b: WhatIfBundle }) {
  return (
    <Panel title={b.label} eyebrow={`${b.n} sessions · last ${Math.round(b.n_days / 7)} weeks`}>
      <p className="mb-5 text-paper">{b.headline}</p>
      <div className="mb-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
        <Stat label="Fitness" value={signed(b.end.fitness_delta)} hint={b.end.fitness_delta_pct != null ? `${signed(b.end.fitness_delta_pct)}% · ${b.end.fitness[0].toFixed(0)} → ${b.end.fitness[1].toFixed(0)}` : undefined} color="#6cc7ff" />
        <Stat label="Average form" value={signed(b.avg_form_delta)} hint="across the window" color="#c8f560" />
        <Stat label="Days above 1.3" value={`${b.acwr_days_over[0]} → ${b.acwr_days_over[1]}`} hint="acute:chronic" />
        {b.performance && <Stat label="Modelled performance" value={b.performance.delta_pct != null ? `${signed(b.performance.delta_pct, 2)}%` : "—"} hint={`personal ${b.performance.taus[0]}/${b.performance.taus[1]}-day model`} />}
      </div>
      <Trajectory rows={b.trajectory} />
      {b.rough && <p className="mt-3 text-xs text-amber">Some sports have too few easy sessions for a personal easy rate, so those were simply halved.</p>}
    </Panel>
  );
}

function Trajectory({ rows }: { rows: WhatIfPoint[] }) {
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [
        { name: "Fitness (actual)", type: "line", symbol: "none", lineStyle: { color: "#6cc7ff", width: 2.5 }, data: rows.map((r) => [r.day, r.fitness]) },
        { name: "Fitness (replay)", type: "line", symbol: "none", lineStyle: { color: "#6cc7ff", width: 2, type: "dashed" }, data: rows.map((r) => [r.day, r.alt_fitness]) },
        { name: "Form (actual)", type: "line", symbol: "none", lineStyle: { color: "#c8f560", width: 2 }, data: rows.map((r) => [r.day, r.form]) },
        { name: "Form (replay)", type: "line", symbol: "none", lineStyle: { color: "#c8f560", width: 1.8, type: "dashed" }, data: rows.map((r) => [r.day, r.alt_form]) },
      ],
    }),
    [rows],
  );
  return (
    <>
      <Chart option={option} height={280} label="Fitness and form: what happened against the replay" />
      <p className="mt-2 flex flex-wrap gap-5 text-xs text-mute"><span>Solid: what happened</span><span>Dashed: the replay</span><span className="text-sky">Fitness</span><span className="text-lime">Form</span></p>
    </>
  );
}

function Custom({ d }: { d: Extract<LabWhatIf, { has_data: true }> }) {
  const [params] = useSearchParams();
  const wanted = Number(params.get("session"));
  const [id, setId] = useState<number | "">(d.recent.some((r) => r.id === wanted) ? wanted : "");
  const [action, setAction] = useState<keyof typeof ACTION_LABEL>("easy");
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");
  const started = useRef(false);
  const run = async (next: number | "", act: keyof typeof ACTION_LABEL) => {
    if (next === "") return;
    setState("loading");
    try {
      setResult(await api.labReplay([{ id: next, action: act }]));
      setState("idle");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't replay that");
      setState("error");
    }
  };
  useEffect(() => {
    if (!started.current && id !== "") {
      started.current = true;
      document.getElementById("replay")?.scrollIntoView({ block: "center" });
      void run(id, action);
    }
  });
  if (!d.recent.length) return null;
  return (
    <div id="replay">
    <Panel title="Replay one session" eyebrow={`Any session with a load from the last ${d.window_days / 7} weeks`}>
      <div className="flex flex-wrap items-end gap-4">
        <label className="min-w-0 flex-1 basis-64">
          <span className="eyebrow">Session</span>
          <select
            value={id} onChange={(e) => { const v = e.target.value === "" ? "" : Number(e.target.value); setId(v); void run(v, action); }}
            className="mt-2 w-full border-b-2 border-line-strong bg-coal py-2 text-paper outline-none focus:border-gold"
          >
            <option value="">Choose…</option>
            {d.recent.map((r) => <option key={r.id} value={r.id}>{formatDate(r.day)} · {r.name} · load {r.load}</option>)}
          </select>
        </label>
        <Segmented label="Change" options={(Object.keys(ACTION_LABEL) as (keyof typeof ACTION_LABEL)[]).map((k) => ({ value: k, label: ACTION_LABEL[k] }))} value={action} onChange={(a) => { setAction(a); void run(id, a); }} />
      </div>
      <div className="mt-6" aria-live="polite">
        {state === "loading" && <LoadingBlock height={120} />}
        {state === "error" && <p className="text-sm text-coral">{error}</p>}
        {state === "idle" && result && (
          <>
            <p className="mb-5 text-paper">{result.headline}</p>
            {result.performance?.delta_pct != null && <p className="mb-4 text-sm text-mute">Your personal model puts performance {signed(result.performance.delta_pct, 2)}% at the end.</p>}
            <Trajectory rows={result.trajectory} />
          </>
        )}
        {state === "idle" && !result && <p className="text-sm text-dim">Pick a session to see the replay.</p>}
      </div>
    </Panel>
    </div>
  );
}
