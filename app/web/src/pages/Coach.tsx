import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Flag, Sparkles, TrendingUp, X } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { NoteGrid, SEVERITY, readyColor } from "../components/CoachNotes";
import { HabitsPanel } from "../components/Journal";
import { StrengthPanel } from "../components/StrengthClass";
import { DemoChip, ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { Sparkline } from "../components/Sparkline";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { Effect, Finding, GoalDistance, Insights, TrainingGoal } from "../lib/types";

type Data = Extract<Insights, { has_data: true }>;

const SEVERITY_KEYS = ["alert", "warn", "info", "good"] as const;
const READY_COLOR = readyColor;
const pace = (s: number) => {
  const r = Math.round(s);
  return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
};
const raceTime = (s: number) => {
  const r = Math.round(s);
  const h = Math.floor(r / 3600);
  const mm = String(Math.floor((r % 3600) / 60)).padStart(h ? 2 : 1, "0");
  return `${h ? `${h}:` : ""}${mm}:${String(r % 60).padStart(2, "0")}`;
};
const clock = (m: number) => {
  const v = ((Math.round(m) % 1440) + 1440) % 1440;
  return `${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`;
};

export function CoachPage() {
  const query = useQuery({
    queryKey: ["insights"],
    queryFn: api.insights,
    refetchInterval: (q) => (q.state.data?.has_data && q.state.data.analysis_running ? 5000 : false),
  });
  if (query.isPending) return <LoadingBlock height={640} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  if (!query.data.has_data) {
    return <div className="surface p-12 text-center text-mute">Sync Garmin data from the Vault to unlock coaching.</div>;
  }
  const d = query.data;
  return (
    <>
      <PageHeader
        eyebrow={
          <>
            Coach · as of {formatDate(d.as_of)} {d.source_id === "demo" && <DemoChip />}
          </>
        }
        title={
          <>
            Train like an <em className="text-gold">athlete.</em>
          </>
        }
      />
      <SectionNav />
      <div className="space-y-6">
        <Readiness d={d} />
        <Plan d={d} />
        <Findings findings={d.findings} />
        <Performance d={d} />
        <Recovery d={d} />
        <Card id="habits" title="Habits" eyebrow="From your journal: what yesterday's choices do to today">
          <HabitsPanel effects={d.habits.effects} progress={d.habits.progress} />
        </Card>
        <Card id="strength" title="Strength" eyebrow="What your named classes trained, last 4 weeks">
          <StrengthPanel s={d.strength_content} />
        </Card>
        <LoadChart d={d} />
        <div className="grid gap-6 xl:grid-cols-2">
          <Intensity d={d} />
          <Weeks d={d} />
        </div>
        <Aerobic d={d} />
        <Sleep d={d} />
        <Effects effects={d.effects} />
        <Methods />
      </div>
    </>
  );
}

const SECTIONS = [
  ["plan", "Plan"], ["findings", "Findings"], ["performance", "Performance"], ["recovery", "Recovery"], ["load", "Load"],
  ["habits", "Habits"], ["strength", "Strength"], ["intensity", "Intensity"], ["aerobic", "Aerobic"], ["sleep", "Sleep"], ["effects", "Patterns"],
] as const;

/** Sticky jump links: the coach page is long, especially on a phone. */
function SectionNav() {
  return (
    <nav
      aria-label="Coach sections"
      className="sticky top-0 z-30 -mx-5 mb-6 flex gap-2 overflow-x-auto border-b border-line bg-ink/90 px-5 py-3 backdrop-blur [scrollbar-width:none] sm:-mx-8 sm:px-8 lg:-mx-12 lg:px-12"
    >
      {SECTIONS.map(([id, label]) => (
        <a key={id} href={`#${id}`} className="chip shrink-0 whitespace-nowrap hover:text-paper pointer-coarse:py-2">
          {label}
        </a>
      ))}
    </nav>
  );
}

function Card({ id, title, eyebrow, aside, children }: { id?: string; title: string; eyebrow?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="surface scroll-mt-20 p-5 sm:p-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
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

// ---- readiness ----------------------------------------------------------------

function Readiness({ d }: { d: Data }) {
  const r = d.readiness;
  const rec = d.recommendation;
  if (!r || !rec) {
    return (
      <Card title="Readiness" eyebrow="Today">
        <p className="text-mute">Needs 14+ days of HRV or resting heart rate before today's score can be computed.</p>
      </Card>
    );
  }
  const color = READY_COLOR(r.score);
  const circ = 2 * Math.PI * 70;
  const labels: Record<string, string> = {
    sleep: "Last night's sleep", sleep_history: "Sleep, last 3 nights", hrv: "HRV status", rhr: "Resting HR",
    load: "Training load", battery: "Body Battery",
  };
  return (
    <section className="relative overflow-hidden border-y border-line py-10">
      <div className="pointer-events-none absolute -top-20 left-10 h-72 w-72 rounded-full opacity-20 blur-3xl" style={{ background: color }} />
      <div className="grid items-center gap-10 lg:grid-cols-[auto_1fr_minmax(0,22rem)]">
        <div className="relative mx-auto h-48 w-48">
          <svg viewBox="0 0 160 160" className="h-full w-full -rotate-90">
            <circle cx="80" cy="80" r="70" fill="none" stroke="#1c1c1f" strokeWidth="10" />
            <motion.circle
              cx="80" cy="80" r="70" fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
              strokeDasharray={circ}
              initial={{ strokeDashoffset: circ }}
              animate={{ strokeDashoffset: circ * (1 - r.score / 100) }}
              transition={{ duration: 1.2, ease: [0.2, 0.9, 0.1, 1] }}
            />
          </svg>
          <div className="absolute inset-0 grid place-items-center text-center">
            <div>
              <p className="num text-6xl" style={{ color }}>{r.score}</p>
              <p className="eyebrow">readiness</p>
            </div>
          </div>
        </div>
        <div>
          <p className="eyebrow mb-2">Today's call</p>
          <h2 className="font-display text-6xl leading-none text-cream">{rec.headline}</h2>
          <p className="mt-4 max-w-xl text-lg text-mute">{rec.detail}</p>
          {d.readiness_history.length > 7 && (
            <div className="mt-6 max-w-md">
              <p className="eyebrow mb-1">Last 90 days</p>
              <Sparkline values={d.readiness_history.map((h) => h.score)} color={color} height={48} />
            </div>
          )}
        </div>
        <div className="space-y-4">
          {Object.entries(r.components).map(([key, c]) => (
            <div key={key}>
              <div className="flex items-baseline justify-between text-sm">
                <span className="text-mute">{labels[key] ?? key}</span>
                <span className="num text-paper">
                  {key === "hrv" && c.value != null && (c.range ? `${c.value} ms · range ${c.range[0]}–${c.range[1]}` : `${c.value} ms · base ${c.baseline}`)}
                  {key === "rhr" && c.value != null && `${c.value} bpm · ${c.delta != null && c.delta >= 0 ? "+" : ""}${c.delta} vs normal`}
                  {key === "sleep" && (c.value != null ? `score ${c.value}` : `${c.hours?.toFixed(1)} h`)}
                  {key === "sleep_history" && c.value != null && `${c.value} h avg${c.need ? ` · need ${c.need} h` : ""}`}
                  {key === "load" && c.acwr != null && `ratio ${c.acwr.toFixed(2)} · form ${c.value != null && c.value > 0 ? "+" : ""}${c.value}`}
                  {key === "battery" && c.value != null && `${c.value}`}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 bg-slate">
                <motion.div
                  className="h-full"
                  style={{ background: READY_COLOR(c.score) }}
                  initial={{ width: 0 }}
                  animate={{ width: `${c.score}%` }}
                  transition={{ duration: 0.9 }}
                />
              </div>
              <p className="mt-1 text-[10px] tracking-widest text-dim uppercase">weight {Math.round(c.weight * 100)}%</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---- weekly plan ----------------------------------------------------------------

const PHASE_COLOR: Record<string, string> = {
  base: "#6cc7ff", build: "#c8f560", specific: "#d9b26a", recovery: "#9b8cff", absorb: "#ffbe55", taper: "#5be3b0", race: "#ff6a55",
};

function Plan({ d }: { d: Data }) {
  const plan = d.plan;
  if (!plan) {
    return (
      <Card id="plan" title="This week" eyebrow="Prescription" aside={<GoalDialog current={d.goal} />}>
        <p className="text-sm text-mute">Needs two complete weeks of training before a plan can be built.</p>
      </Card>
    );
  }
  const color = PHASE_COLOR[plan.phase.phase] ?? "#f2e8cf";
  return (
    <Card
      id="plan"
      title="This week"
      eyebrow={plan.goal ? `${plan.goal.label} · ${formatDate(plan.goal.date)}${plan.goal.target_s ? ` · goal ${raceTime(plan.goal.target_s)}` : ""}` : "Prescription · no race goal set"}
      aside={<GoalDialog current={d.goal} />}
    >
      <div className="mb-6 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="chip" style={{ color, borderColor: `${color}66` }}>{plan.phase.label}{plan.phase.week_in_block && plan.phase.phase !== "race" ? ` · week ${plan.phase.week_in_block}` : ""}</span>
        {plan.phase.weeks_to_race != null && <span className="text-sm text-mute">{plan.phase.weeks_to_race} weeks to race day</span>}
        <p className="w-full text-sm text-mute">{plan.phase.blurb}</p>
      </div>
      {plan.sessions.length > 0 && (
        <div className="mb-6 grid gap-3 md:grid-cols-2">
          {plan.sessions.map((s, i) => (
            <div key={s.kind + i} className="border border-line bg-ink/40 p-5" style={{ borderLeft: `3px solid ${color}` }}>
              <p className="eyebrow mb-2">Quality session {i + 1}</p>
              <p className="font-display text-2xl text-cream">{s.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-mute">{s.detail}</p>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {plan.items.map((item, i) => (
          <motion.div
            key={item.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className="border border-line bg-ink/40 p-4 sm:p-5"
          >
            <p className="eyebrow mb-2">{item.label}</p>
            <p className="num text-xl text-cream sm:text-2xl">{item.value}</p>
            <p className="mt-2 text-xs leading-relaxed text-mute">{item.why}</p>
          </motion.div>
        ))}
      </div>
    </Card>
  );
}

const DISTANCES: { value: GoalDistance; label: string }[] = [
  { value: "5k", label: "5 km" }, { value: "10k", label: "10 km" }, { value: "half", label: "Half" }, { value: "marathon", label: "Marathon" },
];

function parseTime(text: string): number | null {
  const parts = text.trim().split(":").map(Number);
  if (!text.trim() || parts.some((n) => !Number.isFinite(n) || n < 0) || parts.length < 2 || parts.length > 3) return null;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

function GoalDialog({ current }: { current: TrainingGoal | null }) {
  const [open, setOpen] = useState(false);
  const [distance, setDistance] = useState<GoalDistance>(current?.distance ?? "half");
  const [date, setDate] = useState(current?.date ?? "");
  const [time, setTime] = useState(current?.target_s ? raceTime(current.target_s) : "");
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: api.setGoal,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["insights"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setOpen(false);
    },
  });
  const today = new Date().toISOString().slice(0, 10);
  const target = time.trim() ? parseTime(time) : null;
  const timeOk = !time.trim() || (target != null && target >= 600);
  const valid = date >= today && timeOk;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate({ distance, date, target_s: target });
  };
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setDistance(current?.distance ?? "half");
          setDate(current?.date ?? "");
          setTime(current?.target_s ? raceTime(current.target_s) : "");
        }
      }}
    >
      <Dialog.Trigger className="pop">
        <Flag size={16} /> {current ? "Edit race goal" : "Set race goal"}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="surface fixed top-1/2 left-1/2 z-50 w-[min(92vw,480px)] -translate-x-1/2 -translate-y-1/2 p-8">
          <Dialog.Close className="absolute top-4 right-4 p-1 text-mute hover:text-paper" aria-label="Close">
            <X size={18} />
          </Dialog.Close>
          <Dialog.Title className="font-display text-4xl text-cream">Race goal</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-mute">
            The plan counts back from race day: base, build, race-specific weeks, then a taper.
          </Dialog.Description>
          <form onSubmit={submit} className="mt-8 space-y-6">
            <div>
              <p className="eyebrow mb-2">Distance</p>
              <Segmented label="Distance" options={DISTANCES} value={distance} onChange={setDistance} />
            </div>
            <div>
              <label className="eyebrow" htmlFor="goal-date">Race date</label>
              <input
                id="goal-date" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)}
                className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-2xl text-paper outline-none focus:border-gold"
              />
            </div>
            <div>
              <label className="eyebrow" htmlFor="goal-time">Target time (optional)</label>
              <input
                id="goal-time" inputMode="numeric" placeholder="1:45:00" value={time} onChange={(e) => setTime(e.target.value)}
                aria-invalid={!timeOk}
                className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-2xl text-paper outline-none focus:border-gold"
              />
              {!timeOk && <p className="mt-2 text-xs text-coral">Use h:mm:ss or mm:ss.</p>}
              <p className="mt-2 text-xs text-dim">Without one, race-pace sessions use your predicted time.</p>
            </div>
            {save.isError && <p className="text-xs text-coral">Couldn't save. Try again.</p>}
            <div className="flex flex-wrap gap-5">
              <button type="submit" className="pop pop-lime" disabled={!valid || save.isPending}>Save goal</button>
              {current && (
                <button type="button" className="pop pop-ghost" disabled={save.isPending} onClick={() => save.mutate(null)}>Clear</button>
              )}
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ---- performance ----------------------------------------------------------------

function Performance({ d }: { d: Data }) {
  const p = d.performance;
  const cs = p.critical_speed;
  const curveOption = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      xAxis: { ...chartBase.xAxis, type: "value", name: "", axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => `${Math.round(v / 60)} min` } },
      yAxis: { ...chartBase.yAxis, inverse: true, axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => pace(1000 / v) } },
      tooltip: {
        ...chartBase.tooltip,
        trigger: "item",
        formatter: (q: { data: [number, number, string, string] }) => `${Math.round(q.data[0] / 60)} min best<br/><b>${pace(1000 / q.data[1])}/km</b><br/><span style="color:#8d8a82">${q.data[2]} · ${formatDate(q.data[3])}</span>`,
      },
      series: [
        { type: "scatter", data: cs.points.map((x) => [x.seconds, x.speed, x.name, x.day]), symbolSize: 9, itemStyle: { color: "#c8f560" } },
        ...(cs.valid && cs.cs_mps != null && cs.d_prime_m != null
          ? [{
              type: "line", symbol: "none", lineStyle: { color: "#d9b26a", width: 2 },
              data: Array.from({ length: 40 }, (_, i) => 150 + i * 30).map((t) => [t, cs.cs_mps! + cs.d_prime_m! / t]),
            }]
          : []),
      ],
    }),
    [cs],
  );
  const histOption = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      yAxis: { ...chartBase.yAxis, inverse: true, axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => pace(v) } },
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [{ name: "Critical speed", type: "line", data: p.history.map((h) => [h.day, h.pace_s]), symbol: "circle", symbolSize: 6, lineStyle: { color: "#d9b26a", width: 2.5 }, itemStyle: { color: "#d9b26a" } }],
    }),
    [p.history],
  );
  if (!p.analysed_runs && !cs.points.length) {
    return (
      <Card id="performance" title="Performance" eyebrow="Critical speed, race times and form">
        <p className="text-sm text-mute">{d.analysis_pending ? `Analysing ${d.analysis_pending} runs from their FIT files…` : "Needs runs with FIT files."}</p>
      </Card>
    );
  }
  const zc = p.zone_check;
  return (
    <Card id="performance" title="Performance" eyebrow="Critical speed, race times and form · from your FIT files">
      {cs.valid && cs.pace_s ? (
        <div className="mb-8 grid grid-cols-2 gap-6 lg:grid-cols-4">
          <div>
            <p className="eyebrow mb-1">Critical speed</p>
            <p className="num text-4xl text-gold">{pace(cs.pace_s)}<span className="ml-1 text-sm text-mute">/km</span></p>
            <p className="text-xs text-dim">sustainable ~30 min · D′ {cs.d_prime_m} m</p>
          </div>
          {cs.predictions?.map((r) => (
            <div key={r.key} title={r.caveat ?? undefined}>
              <p className="eyebrow mb-1">{r.label}</p>
              <p className="num text-3xl text-paper">{raceTime(r.seconds)}</p>
              <p className="text-xs text-dim">{pace(r.pace_s)}/km{r.caveat ? " · needs long runs" : ""}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mb-6 max-w-2xl text-sm text-mute">
          Critical speed needs {cs.missing ?? "maximal efforts"} in the last {cs.window_days} days. After a thorough warm-up, run 3 minutes all-out,
          jog 30 minutes, then 12 minutes all-out — or race a 5 km. Pace zones and race predictions appear once it fits.
        </p>
      )}
      {cs.valid && cs.paces && (
        <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {cs.paces.map((z) => (
            <div key={z.key} className="border border-line bg-ink/40 p-4">
              <p className="eyebrow mb-1">{z.label}</p>
              <p className="num text-xl text-cream">{pace(z.slow_s)}–{pace(z.fast_s)}<span className="ml-1 text-xs text-mute">/km</span></p>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-8 xl:grid-cols-2">
        <div>
          <p className="eyebrow mb-2">Best efforts, last {cs.window_days} days{cs.valid ? " · gold line is the fitted model" : ""}</p>
          {cs.points.length ? <Chart option={curveOption} height={240} label="Best-effort pace curve" /> : <p className="py-10 text-center text-sm text-dim">No efforts of 3+ minutes yet.</p>}
        </div>
        <div>
          <p className="eyebrow mb-2">Critical speed over the past year</p>
          {p.history.length > 1 ? <Chart option={histOption} height={240} label="Critical speed history" /> : <p className="py-10 text-center text-sm text-dim">Builds up month by month once maximal efforts exist.</p>}
        </div>
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <div className="border border-line bg-ink/40 p-5">
          <p className="eyebrow mb-2">Heart-rate zones</p>
          {zc ? (
            zc.status === "ok" ? (
              <p className="text-sm text-mute">Consistent with your efforts: max {zc.zones_max ?? "—"} bpm, threshold {zc.zones_threshold ?? "—"} bpm{zc.lthr_estimate ? ` (20-min estimate ${zc.lthr_estimate})` : ""}.</p>
            ) : (
              <ul className="space-y-2 text-sm text-amber">{zc.issues.map((i) => <li key={i.key}>{i.detail}</li>)}</ul>
            )
          ) : (
            <p className="text-sm text-dim">Garmin zones not synced yet.</p>
          )}
        </div>
        <div className="border border-line bg-ink/40 p-5">
          <p className="eyebrow mb-2">Running form</p>
          {p.form ? (
            <p className="text-sm text-mute">
              <span className="num text-2xl text-cream">{p.form.cadence_now}</span> spm at {pace(p.form.ref_pace_s)}/km
              {p.form.cadence_before ? ` (was ${p.form.cadence_before})` : ""}
              {p.form.stance_ms ? ` · ground contact ${p.form.stance_ms} ms` : ""}
              {p.form.vertical_ratio ? ` · vertical ratio ${p.form.vertical_ratio}%` : ""}
            </p>
          ) : (
            <p className="text-sm text-dim">Needs 6+ runs with cadence in 90 days.</p>
          )}
        </div>
        <div className="border border-line bg-ink/40 p-5">
          <p className="eyebrow mb-2">Late-run durability</p>
          {p.durability ? (
            <p className="text-sm text-mute">
              Efficiency fades <span className="num text-2xl text-cream">{p.durability.fade_now}%</span> in the last 20 min of long runs
              {p.durability.fade_before != null ? ` (was ${p.durability.fade_before}%)` : ""} · {p.durability.n} runs
            </p>
          ) : (
            <p className="text-sm text-dim">Needs 3+ steady runs over 75 min in 90 days.</p>
          )}
        </div>
      </div>
      {d.analysis_running && <p className="mt-4 text-xs text-gold">Still analysing {d.analysis_pending} runs…</p>}
    </Card>
  );
}

// ---- recovery ---------------------------------------------------------------------

const COMPONENT_NAMES: Record<string, string> = {
  sleep: "sleep", sleep_history: "sleep history", hrv: "HRV", rhr: "resting HR", load: "load", battery: "Body Battery",
};
const KIND_LABEL = { hard: "Hard sessions", long: "Long sessions", easy: "Easy sessions" } as const;

function Recovery({ d }: { d: Data }) {
  const g = d.hrv_guided;
  const rec = d.recovery;
  const v = d.readiness_validation;
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: g
        ? [
            { name: "Normal low", type: "line", stack: "band", data: g.history.map((h) => [h.day, h.low]), symbol: "none", lineStyle: { opacity: 0 } },
            { name: "Normal range", type: "line", stack: "band", data: g.history.map((h) => [h.day, +(h.high - h.low).toFixed(1)]), symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: "rgba(91,227,176,0.12)" } },
            { name: "7-day HRV", type: "line", data: g.history.map((h) => [h.day, h.mean7]), symbol: "none", lineStyle: { color: "#5be3b0", width: 2.5 } },
          ]
        : [],
    }),
    [g],
  );
  const statusColor = !g ? "#8d8a82" : g.status === "below" ? "#ff6a55" : g.coping === "strained" ? "#ffbe55" : "#c8f560";
  return (
    <Card id="recovery" title="Recovery" eyebrow="HRV-guided training and how long your body takes to absorb work">
      {d.warnings && (
        <div className="mb-6 border border-coral/60 bg-coral/10 p-4 text-sm text-paper">
          <b>Early warning:</b> {d.warnings.signals.map((s) => s.label).join(" · ")}. Keep today easy.
        </div>
      )}
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div>
          {g ? (
            <>
              <div className="mb-4 flex flex-wrap items-end gap-8">
                <div>
                  <p className="eyebrow mb-1">HRV-guided</p>
                  <p className="font-display text-4xl" style={{ color: statusColor }}>{g.green_light ? "Green light" : "Keep it easy"}</p>
                  <p className="text-xs text-dim">7-day {g.mean7_ms} ms · normal {g.range_ms[0]}–{g.range_ms[1]} ms</p>
                </div>
                <Big label="Day-to-day swing" value={g.cv7} unit="%" color={g.cv7 > g.cv_base * 1.25 ? "#ffbe55" : "#f2e8cf"} hint={`usual ${g.cv_base.toFixed(1)}%`} digits={1} />
              </div>
              <Chart option={option} height={220} label="7-day HRV against normal range" />
            </>
          ) : (
            <p className="text-sm text-mute">Needs 5 of the last 7 nights and 30 nights of HRV history.</p>
          )}
        </div>
        <div className="space-y-4">
          <p className="eyebrow">Days until HRV is back to normal</p>
          {(["hard", "long", "easy"] as const).map((k) => {
            const r = rec.kinds[k];
            return (
              <div key={k} className="flex items-baseline justify-between border-b border-line pb-2">
                <span className="text-sm text-mute">{KIND_LABEL[k]}</span>
                <span className="num text-xl text-cream">
                  {r.days}
                  <span className="ml-1 text-xs text-dim">{r.personal ? `days · ${r.n} sessions` : "days · default"}</span>
                </span>
              </div>
            );
          })}
          <p className="text-xs text-dim">The plan spaces quality sessions {rec.hard_spacing_days} days apart; live readiness recovers with a {rec.half_life_h} h half-life.</p>
          {v && (
            <div className="border border-line bg-ink/40 p-4 text-xs leading-relaxed text-mute">
              <p className="eyebrow mb-1">Does readiness predict your runs?</p>
              {!v.enough ? (
                <p>Needs 20 comparable runs to check ({v.n} so far).</p>
              ) : (
                <>
                  <p>
                    Correlation with same-day running efficiency: <b className="text-paper">ρ = {v.rho}</b> over {v.n} runs —{" "}
                    {v.predictive ? "readiness is tracking how you actually perform." : "not a clear relationship yet."}
                  </p>
                  {v.suggested_weights && (
                    <p className="mt-2">
                      Weights your data would favour: {Object.entries(v.suggested_weights).map(([k, w]) => `${COMPONENT_NAMES[k] ?? k} ${Math.round(w * 100)}%`).join(", ")}.
                    </p>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---- findings -----------------------------------------------------------------

function Findings({ findings }: { findings: Finding[] }) {
  const [all, setAll] = useState(false);
  const urgent = findings.filter((f) => f.severity === "alert" || f.severity === "warn");
  const shown = all ? findings : urgent.length ? urgent : findings.slice(0, 4);
  const counts = findings.reduce<Record<string, number>>((acc, f) => ({ ...acc, [f.severity]: (acc[f.severity] ?? 0) + 1 }), {});
  return (
    <Card
      id="findings"
      title="What you're missing"
      eyebrow={`${findings.length} findings from your data`}
      aside={
        <div className="flex gap-2">
          {SEVERITY_KEYS.filter((s) => counts[s]).map((s) => (
            <span key={s} className="chip" style={{ color: SEVERITY[s].color, borderColor: `${SEVERITY[s].color}66` }}>
              {counts[s]} {SEVERITY[s].label}
            </span>
          ))}
        </div>
      }
    >
      <NoteGrid notes={shown} />
      {shown.length < findings.length && (
        <button type="button" onClick={() => setAll(true)} className="pop pop-ghost mt-6">
          Show {findings.length - shown.length} more ({findings.length - shown.length === 1 ? "an insight" : "insights"} and what's working)
        </button>
      )}
    </Card>
  );
}

// ---- load ---------------------------------------------------------------------

function LoadChart({ d }: { d: Data }) {
  const [range, setRange] = useState(120);
  const rows = d.pmc.slice(-range);
  const last = d.pmc[d.pmc.length - 1];
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      grid: [
        { left: 8, right: 16, top: 24, height: "52%", containLabel: true },
        { left: 8, right: 16, top: "72%", bottom: 8, containLabel: true },
      ],
      xAxis: [
        { ...chartBase.xAxis, gridIndex: 0, axisLabel: { show: false } },
        { ...chartBase.xAxis, gridIndex: 1 },
      ],
      yAxis: [
        { ...chartBase.yAxis, gridIndex: 0, scale: false },
        { ...chartBase.yAxis, gridIndex: 1, min: 0, max: 2.2, splitNumber: 2 },
      ],
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [
        { name: "Daily load", type: "bar", data: rows.map((r) => [r.day, r.load]), itemStyle: { color: "rgba(217,178,106,0.25)" }, barMaxWidth: 6 },
        { name: "Fitness (42d)", type: "line", data: rows.map((r) => [r.day, r.fitness]), symbol: "none", lineStyle: { color: "#6cc7ff", width: 2.5 } },
        { name: "Fatigue (7d)", type: "line", data: rows.map((r) => [r.day, r.fatigue]), symbol: "none", lineStyle: { color: "#ff6a55", width: 1.5 } },
        {
          name: "Form", type: "line", data: rows.map((r) => [r.day, r.form]), symbol: "none",
          lineStyle: { color: "#c8f560", width: 1.5, type: "dashed" },
        },
        {
          name: "Acute:chronic", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: rows.map((r) => [r.day, r.acwr]), symbol: "none",
          lineStyle: { color: "#f2e8cf", width: 1.8 },
          markArea: {
            silent: true,
            data: [
              [{ yAxis: 0.8, itemStyle: { color: "rgba(200,245,96,0.08)" } }, { yAxis: 1.3 }],
              [{ yAxis: 1.5, itemStyle: { color: "rgba(255,106,85,0.10)" } }, { yAxis: 2.2 }],
            ],
          },
        },
      ],
    }),
    [rows],
  );
  return (
    <Card
      id="load"
      title="Fitness, fatigue & form"
      eyebrow="Banister model on Garmin training load"
      aside={<Segmented label="Range" options={[{ value: 60, label: "60D" }, { value: 120, label: "120D" }, { value: 365, label: "1Y" }]} value={range} onChange={setRange} />}
    >
      <div className="mb-6 grid grid-cols-2 gap-6 sm:grid-cols-4">
        <Big label="Fitness" value={last?.fitness} color="#6cc7ff" hint="42-day load" />
        <Big label="Fatigue" value={last?.fatigue} color="#ff6a55" hint="7-day load" />
        <Big label="Form" value={last?.form} color="#c8f560" hint="fitness − fatigue" signed />
        <Big label="Acute:chronic" value={last?.acwr} color="#f2e8cf" hint="sweet spot 0.8–1.3" digits={2} />
      </div>
      <Chart option={option} height={380} label="Fitness, fatigue and form chart" />
    </Card>
  );
}

function Big({ label, value, color, hint, signed, digits = 0, unit }: { label: string; value: number | null | undefined; color: string; hint?: string; signed?: boolean; digits?: number; unit?: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-4xl" style={{ color }}>
        {value == null ? "—" : `${signed && value > 0 ? "+" : ""}${value.toFixed(digits)}`}
        {value != null && unit && <span className="ml-1 text-sm text-mute">{unit}</span>}
      </p>
      {hint && <p className="text-xs text-dim">{hint}</p>}
    </div>
  );
}

// ---- intensity & weeks ----------------------------------------------------------

function Intensity({ d }: { d: Data }) {
  const weeks = d.weeks.filter((w) => w.easy_pct != null).slice(-16);
  const split = d.intensity_28d;
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      xAxis: { ...chartBase.xAxis, type: "category", data: weeks.map((w) => formatDate(w.week).replace(/ \d{4}$/, "")) },
      yAxis: { ...chartBase.yAxis, max: 100, scale: false, axisLabel: { color: "#5c5a55", fontSize: 10, formatter: "{value}%" } },
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [
        { name: "Easy Z1–2", type: "bar", stack: "z", data: weeks.map((w) => w.easy_pct), itemStyle: { color: "#5be3b0" }, barMaxWidth: 22,
          markLine: { symbol: "none", silent: true, lineStyle: { color: "#f2e8cf", type: "dashed" }, label: { color: "#f2e8cf", formatter: "80% target", position: "insideEndTop" }, data: [{ yAxis: 80 }] } },
        { name: "Moderate Z3", type: "bar", stack: "z", data: weeks.map((w) => w.moderate_pct), itemStyle: { color: "#ffbe55" } },
        { name: "Hard Z4–5", type: "bar", stack: "z", data: weeks.map((w) => w.hard_pct), itemStyle: { color: "#ff6a55" } },
      ],
    }),
    [weeks],
  );
  return (
    <Card id="intensity" title="Intensity balance" eyebrow="Run, ride and swim time by heart-rate zone">
      {split && (
        <div className="mb-6 flex flex-wrap gap-8">
          <Big label="Easy · 28d" value={split.easy_pct} color="#5be3b0" hint="target ~80%" />
          <Big label="Moderate" value={split.moderate_pct} color="#ffbe55" hint="'grey zone'" />
          <Big label="Hard" value={split.hard_pct} color="#ff6a55" />
          {split.hard_sessions_pct != null && <Big label="Hard sessions" value={split.hard_sessions_pct} color="#f2e8cf" hint="target ~20%" />}
          {split.by_sport.run && Object.keys(split.by_sport).length > 1 && <Big label="Runs easy" value={split.by_sport.run.easy_pct} color="#5be3b0" hint="running only" />}
        </div>
      )}
      {weeks.length ? <Chart option={option} height={260} label="Weekly intensity distribution" /> : <p className="text-sm text-dim">No zone data yet.</p>}
    </Card>
  );
}

function Weeks({ d }: { d: Data }) {
  const weeks = d.weeks.slice(-16);
  const families = Array.from(new Set(weeks.flatMap((w) => Object.keys(w.sessions))));
  const colors: Record<string, string> = { run: "#c8f560", strength: "#ff6a55", ride: "#6cc7ff", walk: "#ffbe55", swim: "#5be3b0", mind: "#9b8cff", other: "#5c5a55" };
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      xAxis: { ...chartBase.xAxis, type: "category", data: weeks.map((w) => formatDate(w.week).replace(/ \d{4}$/, "")) },
      yAxis: [{ ...chartBase.yAxis, scale: false, minInterval: 1 }, { ...chartBase.yAxis, scale: false, splitLine: { show: false } }],
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [
        ...families.map((f) => ({
          name: f, type: "bar", stack: "s", data: weeks.map((w) => w.sessions[f] ?? 0), itemStyle: { color: colors[f] ?? "#8d8a82" }, barMaxWidth: 22,
        })),
        { name: "Run km", type: "line", yAxisIndex: 1, data: weeks.map((w) => w.run_km), symbol: "circle", symbolSize: 5, lineStyle: { color: "#f2e8cf" }, itemStyle: { color: "#f2e8cf" } },
      ],
    }),
    [weeks, families],
  );
  const last = d.weeks.filter((w) => w.complete).slice(-1)[0];
  return (
    <Card id="weeks" title="Weekly rhythm" eyebrow="Sessions by type · line is running km">
      {last && (
        <div className="mb-6 flex flex-wrap gap-8">
          <Big label="Last week" value={last.total_sessions} color="#f2e8cf" hint="training sessions" />
          <Big label="Strength" value={last.strength_sessions} color="#ff6a55" hint="target 2" />
          <Big label="Rest days" value={last.rest_days} color="#6cc7ff" />
          <Big label="Monotony" value={last.monotony} color={last.monotony && last.monotony > 2 ? "#ffbe55" : "#f2e8cf"} hint="flag above 2" digits={1} />
        </div>
      )}
      <Chart option={option} height={260} label="Weekly sessions" />
    </Card>
  );
}

// ---- aerobic engine ------------------------------------------------------------

function Aerobic({ d }: { d: Data }) {
  const t = d.efficiency.trend;
  const ref = t?.ref_hr ?? 150;
  const runs = d.efficiency.runs;
  const effOption = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      yAxis: { ...chartBase.yAxis, inverse: true, axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => pace(v) } },
      tooltip: {
        ...chartBase.tooltip,
        trigger: "item",
        formatter: (p: { data: [string, number, string] }) => `${formatDate(p.data[0])}<br/><b>${pace(p.data[1])}/km</b> at ${ref} bpm<br/><span style="color:#8d8a82">${p.data[2]}</span>`,
      },
      series: [
        { type: "scatter", data: runs.map((r) => [r.day, r.pace_s, r.name]), symbolSize: 6, itemStyle: { color: "rgba(200,245,96,0.45)" } },
        { type: "line", data: (t?.monthly ?? []).map((m) => [`${m.month}-15`, m.pace_s]), symbol: "circle", symbolSize: 6, lineStyle: { color: "#c8f560", width: 2.5 }, itemStyle: { color: "#c8f560" } },
      ],
    }),
    [runs, t, ref],
  );
  const dur = d.durability;
  const durOption = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      yAxis: { ...chartBase.yAxis, axisLabel: { color: "#5c5a55", fontSize: 10, formatter: "{value}%" } },
      tooltip: {
        ...chartBase.tooltip,
        trigger: "item",
        formatter: (p: { data: [string, number, string, number, boolean] }) => `${formatDate(p.data[0])} · ${p.data[3]} min<br/><b>${p.data[1]}% drift</b>${p.data[4] ? "" : " (unsteady pace)"}<br/><span style="color:#8d8a82">${p.data[2]}</span>`,
      },
      series: [
        {
          type: "scatter",
          data: dur.map((r) => ({ value: [r.day, r.decoupling_pct, r.name, r.minutes, r.steady], itemStyle: { color: r.steady ? (r.decoupling_pct > 5 ? "#ffbe55" : "#5be3b0") : "#34343a" } })),
          symbolSize: (v: [string, number, string, number]) => Math.max(6, Math.min(18, v[3] / 8)),
          markLine: { symbol: "none", silent: true, lineStyle: { color: "#ff6a55", type: "dashed" }, label: { color: "#ff6a55", formatter: "5% benchmark", position: "insideEndTop" }, data: [{ yAxis: 5 }] },
        },
      ],
    }),
    [dur],
  );
  const vo2Option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      series: [{ type: "line", data: d.vo2max.map((v) => [v.day, v.value]), symbol: "none", step: "end", lineStyle: { color: "#d9b26a", width: 2.5 }, areaStyle: { color: "rgba(217,178,106,0.08)" } }],
    }),
    [d.vo2max],
  );
  return (
    <Card id="aerobic" title="Aerobic engine" eyebrow="Are you getting fitter at the same effort?">
      <div className="mb-8 grid grid-cols-2 gap-6 lg:grid-cols-3">
        <div>
          <p className="eyebrow mb-1">Pace @ {ref} bpm</p>
          <p className="num text-4xl text-lime">{t ? `${pace(t.pace_now_s)}` : "—"}<span className="ml-1 text-sm text-mute">/km</span></p>
          {t?.pace_90d_ago_s && <p className="text-xs text-dim">was {pace(t.pace_90d_ago_s)} 90 days ago</p>}
        </div>
        <div>
          <p className="eyebrow mb-1">90-day change</p>
          <p className={clsx("num text-4xl", t?.significant ? (t.change_pct_90d! > 0 ? "text-lime" : "text-amber") : "text-paper")}>
            {t?.change_pct_90d != null ? `${t.change_pct_90d > 0 ? "+" : ""}${t.change_pct_90d}%` : "—"}
          </p>
          <p className="text-xs text-dim">{t ? (t.significant ? "statistically clear" : "within noise") : ""}</p>
        </div>
        {d.vo2max.length > 0 && <Big label="VO₂ max" value={d.vo2max.at(-1)?.value} color="#d9b26a" hint="Garmin estimate" />}
      </div>
      <div className="grid gap-8 xl:grid-cols-2">
        <div>
          <p className="eyebrow mb-2 flex items-center gap-2"><TrendingUp size={12} /> Pace at {ref} bpm · each dot a run, line is monthly median</p>
          <Chart option={effOption} height={280} label="Aerobic efficiency trend" />
        </div>
        <div>
          <p className="eyebrow mb-2">Heart-rate drift on runs over 45 min (grade-adjusted) · grey = unsteady pace</p>
          {dur.length ? (
            <Chart option={durOption} height={280} label="Aerobic decoupling" />
          ) : (
            <p className="py-12 text-center text-sm text-dim">
              {d.analysis_pending ? `Analysing ${d.analysis_pending} long runs from their FIT files…` : "No long runs yet."}
            </p>
          )}
          {d.analysis_running && dur.length > 0 && <p className="mt-2 text-xs text-gold">Still analysing {d.analysis_pending} runs…</p>}
        </div>
      </div>
      {d.vo2max.length > 1 && (
        <div className="mt-8">
          <p className="eyebrow mb-2">VO₂ max</p>
          <Chart option={vo2Option} height={160} label="VO2 max trend" />
        </div>
      )}
    </Card>
  );
}

// ---- sleep ------------------------------------------------------------------------

function Sleep({ d }: { d: Data }) {
  const p = d.sleep.pattern_14d;
  const nights = d.sleep.nights;
  const need = d.sleep.need.hours;
  const sri = d.sleep.regularity;
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      yAxis: {
        ...chartBase.yAxis, type: "value", inverse: true, scale: false, min: -180, max: 720,
        axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => clock(v) },
      },
      tooltip: {
        ...chartBase.tooltip,
        trigger: "item",
        formatter: (q: { data: [string, number, number, number] }) => `${formatDate(q.data[0])}<br/>${clock(q.data[1])} → ${clock(q.data[2])}<br/><b>${q.data[3]?.toFixed(1)} h</b>`,
      },
      series: [
        {
          type: "custom",
          data: nights.filter((n) => n.bedtime != null && n.wake != null).map((n) => [n.day, n.bedtime, n.wake, n.hours]),
          renderItem: (_: unknown, api: { value: (i: number) => number; coord: (p: [number, number]) => [number, number]; size: (p: [number, number]) => [number, number] }) => {
            const start = api.coord([api.value(0), api.value(1)]);
            const end = api.coord([api.value(0), api.value(2)]);
            const width = Math.max(3, api.size([86_400_000, 0])[0] * 0.6);
            const hours = api.value(3);
            return { type: "rect", shape: { x: start[0] - width / 2, y: start[1], width, height: end[1] - start[1] }, style: { fill: hours >= need - 0.25 ? "#6cc7ff" : "#ffbe55", opacity: 0.85 } };
          },
          markArea: { silent: true, itemStyle: { color: "rgba(255,255,255,0.03)" }, data: [[{ yAxis: -60 }, { yAxis: 0 }]] },
        },
      ],
    }),
    [nights, need],
  );
  return (
    <Card id="sleep" title="Sleep timing" eyebrow={`Each bar is a night · amber = under your ${need} h need`}>
      <p className="mb-6 max-w-3xl text-sm text-mute">
        <b className="text-paper">Your need: {need} h.</b> {d.sleep.need.detail}
      </p>
      {d.sleep.tonight && (
        <div className="mb-6 border border-line bg-ink/40 p-5">
          <p className="eyebrow mb-1">Tonight</p>
          <p className="text-lg text-paper">
            In bed by <span className="num text-sky">{clock(d.sleep.tonight.bed_min)}</span>, asleep by {clock(d.sleep.tonight.lights_out_min)}, up at {clock(d.sleep.tonight.wake_min)}
            <span className="text-mute"> · {d.sleep.tonight.tonight_h.toFixed(1)} h</span>
          </p>
          <p className="mt-1 text-xs text-dim">
            {need} h need{d.sleep.tonight.extra_load_min ? ` + ${d.sleep.tonight.extra_load_min} min for today's training` : ""}
            {d.sleep.tonight.repay_min ? ` + ${d.sleep.tonight.repay_min} min toward ${d.sleep.tonight.debt_h} h of debt` : ""} · wake time is your usual for {d.sleep.tonight.weekend ? "weekends" : "weekdays"}, 15 min to fall asleep.
            {d.sleep.tonight.capped && ` The full ${d.sleep.tonight.ideal_h.toFixed(1)} h would mean going to bed far earlier than you're used to, so tonight is capped at an hour earlier than usual: shift a little more each night.`}
          </p>
          {d.sleep.target_check && (
            <p className="mt-2 text-xs text-mute">
              {d.sleep.target_check.significant
                ? `On your history, nights that reach the target are followed by ${d.sleep.target_check.diff > 0 ? "+" : ""}${d.sleep.target_check.diff.toFixed(1)} ms HRV (${d.sleep.target_check.n_exposed} vs ${d.sleep.target_check.n_reference} nights, allowing for training load).`
                : `Nights at target vs short of it don't differ clearly in HRV yet (${d.sleep.target_check.n_exposed} vs ${d.sleep.target_check.n_reference} nights).`}
            </p>
          )}
        </div>
      )}
      {p && (
        <div className="mb-6 grid grid-cols-2 gap-6 sm:grid-cols-5">
          <Big label="Avg sleep · 14d" value={p.avg_hours} color={p.avg_hours >= need - 0.25 ? "#6cc7ff" : "#ffbe55"} digits={1} hint="hours" />
          <div>
            <p className="eyebrow mb-1">Avg bedtime</p>
            <p className="num text-4xl text-paper">{p.avg_bedtime_min != null ? clock(p.avg_bedtime_min) : "—"}</p>
            {p.bedtime_sd_min != null && <p className="text-xs text-dim">± {p.bedtime_sd_min} min</p>}
          </div>
          <div>
            <p className="eyebrow mb-1">Avg wake</p>
            <p className="num text-4xl text-paper">{p.avg_wake_min != null ? clock(p.avg_wake_min) : "—"}</p>
            {p.wake_sd_min != null && <p className="text-xs text-dim">± {p.wake_sd_min} min</p>}
          </div>
          <Big label="7-day debt" value={p.debt_hours} color="#ffbe55" digits={1} hint={`hours vs ${need} h/night`} />
          {sri && <Big label="Regularity" value={sri.sri} color={sri.sri >= 80 ? "#6cc7ff" : "#ffbe55"} hint={`SRI · midpoint ±${sri.midpoint_sd_min} min`} />}
        </div>
      )}
      {nights.some((n) => n.bedtime != null) ? (
        <Chart option={option} height={300} label="Sleep timing" />
      ) : (
        <p className="text-sm text-dim">Bedtimes appear after the next offline rebuild from the vault.</p>
      )}
    </Card>
  );
}

// ---- lagged effects ----------------------------------------------------------------

function Effects({ effects }: { effects: Effect[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? effects : effects.filter((e) => e.significant);
  return (
    <Card
      id="effects"
      title="What moves your recovery"
      eyebrow="Your own data, compared day against day"
      aside={
        <button type="button" onClick={() => setAll((a) => !a)} className="eyebrow hover:text-paper">
          {all ? "Only clear effects" : `Show all ${effects.length} tested`}
        </button>
      }
    >
      {shown.length === 0 ? (
        <p className="text-sm text-mute">No clear effects yet — more days of data sharpen these comparisons.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((e) => {
            const better = e.higher_is_better ? e.diff > 0 : e.diff < 0;
            const color = !e.significant ? "#8d8a82" : better ? "#c8f560" : "#ff6a55";
            return (
              <div key={e.id} className="border border-line bg-ink/40 p-5">
                <p className="eyebrow mb-2">{e.cause} → {e.outcome}</p>
                <p className="text-paper">
                  <span className="font-semibold">{e.exposed}</span>
                  <span className="text-mute"> vs {e.reference.toLowerCase()}</span>
                </p>
                <p className="num mt-3 text-4xl" style={{ color }}>
                  {e.diff > 0 ? "+" : ""}{e.diff.toFixed(1)}
                  <span className="ml-1 text-sm text-mute">{e.unit || "pts"}</span>
                </p>
                <p className="text-xs text-dim">
                  {e.exposed_mean.toFixed(1)} vs {e.reference_mean.toFixed(1)} · {e.pct > 0 ? "+" : ""}{e.pct}% · n = {e.n_exposed} / {e.n_reference}
                </p>
                <p className={clsx("mt-2 text-xs", e.significant ? "text-paper" : "text-dim")}>
                  {e.significant
                    ? `Clear difference (q = ${e.q_value < 0.001 ? "<0.001" : e.q_value.toFixed(3)})`
                    : `Could be noise (q = ${e.q_value.toFixed(2)})`}
                  {e.adjusted_for.length > 0 && <span className="text-dim"> · allowing for {e.adjusted_for.join(" and ")}</span>}
                </p>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-6 text-xs text-dim">
        Associations, not proof of cause. Each comparison allows for that day's training load and weekends where relevant, widens its uncertainty
        for day-to-day carry-over, and is called “clear” only when it survives a false-discovery correction across all {effects.length} tests (q &lt; 0.05).
      </p>
    </Card>
  );
}

function Methods() {
  return (
    <details className="surface p-6 text-sm text-mute">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-paper">
        <Sparkles size={16} className="text-gold" /> How the coach works
      </summary>
      <ul className="mt-4 max-w-3xl list-disc space-y-2 pl-5 leading-relaxed">
        <li><b className="text-paper">Readiness</b>: modelled on Garmin's Training Readiness factors. Last night's sleep score (25%), last 3 nights vs your sleep need (10%), HRV against your Garmin balanced range (25%), resting HR in bpm vs your 60-day normal (15%), training load from acute:chronic ratio and form (20%) and morning Body Battery (5%, since it is itself built from HRV and sleep). A typical, well-recovered day scores about 80; missing parts are re-weighted. Its link to your same-day running efficiency is checked, and suggested weights are shown, never applied silently.</li>
        <li><b className="text-paper">HRV-guided training</b>: 7-day rolling ln RMSSD against a 60-day normal range of ±0.5 SD (Plews; Kiviniemi). Below it, sessions stay easy; rising day-to-day variation with a falling mean signals poor coping.</li>
        <li><b className="text-paper">Recovery cost</b>: days for next-morning HRV to return to its pre-session level after isolated hard, long and easy sessions; sets quality-session spacing and the live-readiness half-life.</li>
        <li><b className="text-paper">Plan</b>: phases count back from your race (taper 1–3 weeks by distance, 6 race-specific, 8 build, base before); without a goal, a recovery week follows three building weeks. Load ramps fitness ~2–5 points a week, capped at 1.25 × chronic load; long runs grow 10 minutes a week and never exceed the longest run of the last 30 days by more than 10% (Frandsen et al. 2025).</li>
        <li><b className="text-paper">Critical speed</b>: linear distance–time model on your best grade-adjusted 3–20 minute efforts (last 90 days), trusted only when D′ is physiological. Race times: CS model to 5 km, Riegel (1.06) beyond.</li>
        <li><b className="text-paper">Fitness / fatigue / form</b>: 42- and 7-day exponentially weighted Garmin training load (Banister). Form is yesterday's fitness minus fatigue.</li>
        <li><b className="text-paper">Acute:chronic ratio</b>: 7-day vs 28-day EWMA load. A weak injury predictor alone, so it only alerts when running volume spikes too; recovery weeks have their own band.</li>
        <li><b className="text-paper">Intensity balance</b>: heart-rate zone time on runs, rides and swims (walks excluded), plus the share of hard sessions; sprint sessions count as hard by anaerobic training effect.</li>
        <li><b className="text-paper">Aerobic efficiency</b>: grade-adjusted speed per beat above resting HR on non-interval runs ≥ 3 km (running VO₂ is linear in speed, and %VO₂ reserve tracks %HR reserve), shown as pace at your median running HR; Theil–Sen trend.</li>
        <li><b className="text-paper">Heart-rate drift and durability</b>: Pa:HR decoupling on grade-adjusted pace (Minetti), first vs second half after a 10-minute warm-up; late-run fade compares the last 20 minutes of 75-minute-plus runs with minutes 10–30.</li>
        <li><b className="text-paper">Sleep</b>: your need is where more sleep stops lifting overnight HRV (8 h until your data shows a plateau); regularity is the Sleep Regularity Index from onset and wake times.</li>
      </ul>
    </details>
  );
}
