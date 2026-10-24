import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Bike, Check, Flag, Footprints, Plus, Route, Scale, Target, Trash2, Waves, X } from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { formatDate } from "../lib/format";
import { clockTime as hms, countdown, distanceLabel as km, pacePer, parseTime, signed } from "../lib/goals";
import type { GoalBand, GoalInput, GoalKind, GoalSport, GoalsResponse, GoalView } from "../lib/types";

const KIND_LABEL: Record<GoalKind, string> = { race: "Race", performance: "Target", distance: "Distance", weight: "Weight" };
const KIND_HELP: Record<GoalKind, string> = {
  race: "An event on a date. The plan counts back from it.",
  performance: "A time or average speed over a distance, with or without a date.",
  distance: "Go this far in one session.",
  weight: "A target scale weight, judged on the trend line.",
};
const SPORT_ICON = { run: Footprints, ride: Bike, swim: Waves } as const;
const BAND_COLOR: Record<GoalBand, string> = { likely: "#c8f560", plausible: "#5be3b0", "a stretch": "#ffbe55", unlikely: "#ff6a55" };
const PHASE_COLOR: Record<string, string> = {
  base: "#6cc7ff", build: "#d9b26a", specific: "#ff6a55", recovery: "#5be3b0", absorb: "#ffbe55", taper: "#9b8cff", race: "#c8f560",
};
const PRESETS: Record<GoalSport, { label: string; m: number }[]> = {
  run: [{ label: "5 km", m: 5000 }, { label: "10 km", m: 10000 }, { label: "Half", m: 21097.5 }, { label: "Marathon", m: 42195 }],
  ride: [{ label: "20 km", m: 20000 }, { label: "40 km", m: 40000 }, { label: "100 km", m: 100000 }, { label: "160 km", m: 160000 }],
  swim: [{ label: "400 m", m: 400 }, { label: "1.5 km", m: 1500 }, { label: "1.9 km", m: 1900 }, { label: "3.8 km", m: 3800 }],
};

export function GoalsPage() {
  const q = useQuery({ queryKey: ["goals"], queryFn: api.goals });
  const [editing, setEditing] = useState<GoalView | "new" | null>(null);
  return (
    <>
      <PageHeader eyebrow="Where you're heading" title={<>Your <em className="text-gold">goals.</em></>}>
        {!READ_ONLY && (
          <button type="button" className="pop" onClick={() => setEditing("new")}><Plus size={16} /> New goal</button>
        )}
      </PageHeader>
      {q.isPending ? <LoadingBlock height={420} /> : q.isError ? <ErrorBlock error={q.error} retry={() => q.refetch()} /> : (
        <Body d={q.data} edit={(g) => setEditing(g)} />
      )}
      {!READ_ONLY && <GoalDialog target={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function Body({ d, edit }: { d: GoalsResponse; edit: (g: GoalView) => void }) {
  const active = d.goals.filter((g) => g.status === "active");
  const closed = d.goals.filter((g) => g.status !== "active");
  if (!d.goals.length) {
    return (
      <div className="surface p-10 text-center">
        <Flag size={28} className="mx-auto mb-4 text-gold" />
        <p className="font-display text-3xl text-cream">Nothing to aim at yet.</p>
        <p className="mx-auto mt-3 max-w-xl text-sm text-mute">
          Set a race, a target time or speed, a distance you want to cover in one go, or a weight. Cadence says how reachable it looks from your own data, with the uncertainty, and what the weeks ahead should look like.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      {!d.has_training && <p className="surface p-5 text-sm text-mute">No training data yet, so run, ride and swim goals can't be assessed. Weight goals can.</p>}
      {active.map((g) => <GoalCard key={g.id} g={g} planGoal={g.id === d.plan_goal_id} edit={edit} />)}
      {!active.length && <p className="text-sm text-mute">No active goals.</p>}
      {closed.length > 0 && (
        <details className="surface p-5 text-sm">
          <summary className="cursor-pointer font-semibold text-paper">Past goals ({closed.length})</summary>
          <ul className="mt-4 space-y-2">
            {closed.map((g) => <ClosedRow key={g.id} g={g} />)}
          </ul>
        </details>
      )}
      <p className="max-w-3xl text-xs leading-relaxed text-dim">
        The weekly plan follows the nearest upcoming run race at 5 km, 10 km, a half or a full marathon; other goals are assessed here and do not change the plan. Outlooks are bands from your own history, not predictions: the run model samples your critical speed and its trend, ride and swim use your best recent sessions, and weight uses the trend line. None of it is medical advice.
      </p>
    </div>
  );
}

function useGoalMutations() {
  const client = useQueryClient();
  const refresh = () => {
    for (const k of ["goals", "insights", "overview", "weight", "planner"]) client.invalidateQueries({ queryKey: [k] });
  };
  return {
    patch: useMutation({ mutationFn: ({ id, ...p }: { id: number; status?: GoalView["status"] }) => api.updateGoal(id, p), onSuccess: refresh }),
    remove: useMutation({ mutationFn: api.deleteGoal, onSuccess: refresh }),
    refresh,
  };
}

function ClosedRow({ g }: { g: GoalView }) {
  const m = useGoalMutations();
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 pb-2">
      <span className="text-paper">{g.title} <span className="text-xs text-dim">{g.status === "achieved" ? "achieved" : "dropped"}{g.closed_on ? ` ${formatDate(g.closed_on)}` : ""}</span></span>
      {!READ_ONLY && (
        <span className="flex gap-4 text-xs">
          <button type="button" className="text-mute hover:text-paper" onClick={() => m.patch.mutate({ id: g.id, status: "active" })}>Reopen</button>
          <button type="button" className="text-mute hover:text-coral" onClick={() => m.remove.mutate(g.id)}>Delete</button>
        </span>
      )}
    </li>
  );
}

function GoalCard({ g, planGoal, edit }: { g: GoalView; planGoal: boolean; edit: (g: GoalView) => void }) {
  const m = useGoalMutations();
  const Icon = g.kind === "weight" ? Scale : g.sport ? SPORT_ICON[g.sport] : Target;
  const when = countdown(g);
  const band = g.outlook?.band;
  return (
    <section className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <Icon size={22} className="mt-1.5 shrink-0 text-gold" />
          <div className="min-w-0">
            <p className="eyebrow mb-1 flex flex-wrap items-center gap-2">
              {KIND_LABEL[g.kind]}{g.sport ? ` · ${g.sport}` : ""}{g.date ? ` · ${formatDate(g.date)}` : ""}{when ? ` · ${when}` : ""}
              {planGoal && <span className="chip !border-gold/40 !text-gold">Drives the plan</span>}
            </p>
            <h2 className="font-display text-3xl text-cream sm:text-4xl">{g.title}</h2>
          </div>
        </div>
        {band && (
          <div className="text-right">
            <p className="eyebrow mb-1">{g.outlook?.heuristic ? "Outlook (heuristic)" : "Outlook"}</p>
            <p className="font-display text-3xl capitalize" style={{ color: BAND_COLOR[band] }}>{band}</p>
            {g.outlook?.probability != null && <p className="num text-xs text-dim">{g.outlook.probability >= 0.95 ? "over 95%" : g.outlook.probability <= 0.05 ? "under 5%" : `about ${Math.round(g.outlook.probability * 100)}%`}</p>}
          </div>
        )}
      </div>
      <p className="mt-4 max-w-3xl text-paper" style={{ borderLeft: `3px solid ${g.headline.tone === "good" ? "#c8f560" : g.headline.tone === "warn" ? "#ffbe55" : "#34343a"}`, paddingLeft: 12 }}>
        {g.headline.text}
      </p>
      {g.state === "ok" && (
        <div className="mt-6 space-y-6">
          {(g.kind === "race" || g.kind === "performance") && <PerformanceDetail g={g} />}
          {g.kind === "distance" && <DistanceDetail g={g} />}
          {g.kind === "weight" && <WeightDetail g={g} />}
          {g.roadmap && g.roadmap.length > 1 && <Roadmap g={g} />}
          {g.caveats && g.caveats.length > 0 && (
            <ul className="space-y-1 text-xs text-dim">{g.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
          )}
        </div>
      )}
      {!READ_ONLY && (
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 border-t border-line pt-4 text-xs font-semibold tracking-widest uppercase">
          <button type="button" className={clsx("flex items-center gap-1.5", g.achieved_hint ? "text-lime" : "text-mute hover:text-paper")} onClick={() => m.patch.mutate({ id: g.id, status: "achieved" })}><Check size={14} /> Mark achieved</button>
          <button type="button" className="text-mute hover:text-paper" onClick={() => edit(g)}>Edit</button>
          <button type="button" className="text-mute hover:text-paper" onClick={() => m.patch.mutate({ id: g.id, status: "dropped" })}>Drop</button>
          <button type="button" className="flex items-center gap-1.5 text-mute hover:text-coral" onClick={() => m.remove.mutate(g.id)}><Trash2 size={14} /> Delete</button>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, hint, color }: { label: string; value: ReactNode; hint?: ReactNode; color?: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-2xl" style={{ color: color ?? "#f2e8cf" }}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-dim">{hint}</p>}
    </div>
  );
}

function PerformanceDetail({ g }: { g: GoalView }) {
  const dist = g.spec.distance_m ?? 0;
  const target = g.spec.target_s;
  const p = g.projected;
  // The range bar spans the projected 10th–90th percentile and the target, so "inside the bar" reads as "reachable".
  const lo = Math.min(p?.p10_s ?? Infinity, target ?? Infinity, g.current_s ?? Infinity);
  const hi = Math.max(p?.p90_s ?? 0, target ?? 0, g.current_s ?? 0);
  const at = (s: number) => `${((s - lo) / Math.max(hi - lo, 1)) * 100}%`;
  return (
    <>
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        {g.current_s != null && <Stat label="Today's level" value={hms(g.current_s)} hint={`${pacePer(g.sport, dist, g.current_s)} · ${g.basis}`} color="#6cc7ff" />}
        {target != null && <Stat label="Target" value={hms(target)} hint={pacePer(g.sport, dist, target)} color="#d9b26a" />}
        {p && <Stat label={g.date ? "By the date" : `In ${Math.round((g.horizon_days ?? 84) / 7)} weeks`} value={hms(p.p50_s)} hint={`middle 80%: ${hms(p.p10_s)}–${hms(p.p90_s)}`} />}
        {g.cs_gain_pct != null && <Stat label="Needs" value={g.cs_gain_pct <= 0 ? "met" : `+${g.cs_gain_pct}% speed`} hint="critical speed for the target" color={g.cs_gain_pct <= 0 ? "#c8f560" : "#ffbe55"} />}
        {g.outlook?.required_gain_pct != null && g.cs_gain_pct == null && (
          <Stat label="Still to find" value={g.outlook.required_gain_pct <= 0 ? "none" : `${g.outlook.required_gain_pct}%`} hint={g.outlook.per_month_pct != null ? `${g.outlook.per_month_pct}% a month` : "already shown"} color={g.outlook.required_gain_pct <= 0 ? "#c8f560" : "#ffbe55"} />
        )}
      </div>
      {p && target != null && Number.isFinite(lo) && (
        <div>
          <div className="relative h-3 bg-line" role="img" aria-label={`Projected finish between ${hms(p.p10_s)} and ${hms(p.p90_s)}, target ${hms(target)}`}>
            <div className="absolute inset-y-0 bg-sky/40" style={{ left: at(p.p10_s), right: `calc(100% - ${at(p.p90_s)})` }} />
            <div className="absolute -top-1 -bottom-1 w-0.5 bg-gold" style={{ left: at(target) }} />
            {g.current_s != null && <div className="absolute inset-y-0 w-0.5 bg-cream" style={{ left: at(g.current_s) }} />}
          </div>
          <p className="mt-2 flex flex-wrap gap-4 text-xs text-dim"><span className="text-sky">▬ projected range</span><span className="text-gold">| target</span><span className="text-cream">| today</span><span>faster ← → slower</span></p>
        </div>
      )}
      {g.demonstrated && (
        <p className="text-xs text-dim">
          Best matching session: <Link to={`/activities/${g.demonstrated.id}`} className="text-mute hover:text-gold">{g.demonstrated.name}</Link> ({formatDate(g.demonstrated.day)}, {km(g.demonstrated.distance_m)}).
        </p>
      )}
    </>
  );
}

function DistanceDetail({ g }: { g: GoalView }) {
  const target = g.spec.distance_m ?? 0;
  const weeks = g.ladder?.weeks ?? [];
  return (
    <>
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        <Stat label="Longest, last 90 days" value={g.longest_recent ? km(g.longest_recent.distance_m) : "—"} color="#6cc7ff" />
        <Stat label="Target" value={km(target)} color="#d9b26a" />
        {g.ladder && <Stat label="Weeks needed" value={g.ladder.weeks_needed} hint={g.earliest ? `earliest ${formatDate(g.earliest)}` : undefined} />}
        {g.outlook?.spare_weeks != null && <Stat label="Spare weeks" value={signed(g.outlook.spare_weeks, 0)} color={g.outlook.spare_weeks >= 0 ? "#c8f560" : "#ff6a55"} />}
      </div>
      {weeks.length > 0 && (
        <div>
          <p className="eyebrow mb-2">Long-session ladder</p>
          <div className="flex items-end gap-1" style={{ height: 96 }} role="img" aria-label="Weekly long-session distances up to the attempt">
            {weeks.slice(0, 40).map((w) => (
              <div key={w.week} className="flex min-w-0 flex-1 flex-col items-center justify-end" title={`Week ${w.week}: ${km(w.m)} (${w.kind})`}>
                <div className="w-full" style={{ height: `${Math.max(4, (w.m / target) * 88)}px`, background: w.kind === "attempt" ? "#c8f560" : w.kind === "recovery" ? "#5be3b0" : w.kind === "easier" ? "#34343a" : "#d9b26a" }} />
              </div>
            ))}
          </div>
          <p className="mt-2 flex flex-wrap gap-4 text-xs text-dim"><span className="text-gold">▬ build</span><span className="text-mint">▬ recovery (75%)</span><span>▬ easier week</span><span className="text-lime">▬ attempt</span></p>
        </div>
      )}
    </>
  );
}

function WeightDetail({ g }: { g: GoalView }) {
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      series: [{ name: "Straight line to the target", type: "line", symbol: "none", lineStyle: { color: "#d9b26a", width: 2, type: "dashed" }, data: (g.path ?? []).map((p) => [p.week, p.kg]) }],
    }),
    [g.path],
  );
  const proj = g.projection;
  return (
    <>
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        <Stat label="Trend now" value={`${g.current_kg} kg`} color="#6cc7ff" />
        <Stat label="Target" value={`${g.target_kg} kg`} hint={g.gap_kg != null ? `${signed(g.gap_kg)} kg to go` : undefined} color="#d9b26a" />
        <Stat label="Recent rate" value={g.rate_kg_wk != null ? `${signed(g.rate_kg_wk, 2)} kg/wk` : "—"} hint={g.rate_pct_wk != null ? `${signed(g.rate_pct_wk, 2)}% of body weight` : "needs 8+ weigh-ins in 4 weeks"} color={g.rate_flag ? "#ffbe55" : undefined} />
        {g.required ? (
          <Stat label="Date needs" value={`${signed(g.required.kg_wk, 2)} kg/wk`} hint={`${signed(g.required.pct_wk, 2)}%/wk${g.required.too_fast ? " · faster than advised" : ""}`} color={g.required.too_fast ? "#ff6a55" : "#c8f560"} />
        ) : (
          <Stat label="Steady pace" value={g.steady ? formatDate(g.steady) : "—"} hint="at 0.5% of body weight a week" />
        )}
      </div>
      {g.progress_pct != null && (
        <div>
          <div className="h-2 bg-line" role="progressbar" aria-valuenow={g.progress_pct} aria-valuemin={0} aria-valuemax={100} aria-label="Progress from the starting weight"><div className="h-full bg-gold" style={{ width: `${g.progress_pct}%` }} /></div>
          <p className="mt-1 text-xs text-dim">{g.progress_pct}% from {g.start_value} kg</p>
        </div>
      )}
      {g.path && g.path.length > 1 && <Chart option={option} height={200} label="Straight-line weight path to the target date" />}
      {proj && proj.status === "on_track" && proj.expected && (
        <p className="text-sm text-mute">At the current rate: {formatDate(proj.expected)}{proj.earliest && proj.latest ? ` (between ${formatDate(proj.earliest)} and ${formatDate(proj.latest)})` : ""}.</p>
      )}
      {g.earliest_safe && <p className="text-xs text-dim">Fastest pace usually compatible with training well (1% of body weight a week for loss, 0.5% for gain): {formatDate(g.earliest_safe)}.</p>}
    </>
  );
}

function Roadmap({ g }: { g: GoalView }) {
  const weeks = g.roadmap ?? [];
  const phases = [...new Map(weeks.map((w) => [w.phase, w.label])).entries()];
  return (
    <div>
      <p className="eyebrow mb-2">Weeks to go · {weeks.length - 1}</p>
      <div className="flex gap-1" role="img" aria-label={`Training phases from now to ${g.date ?? "the goal"}`}>
        {weeks.map((w) => (
          <div key={w.week} className="h-6 min-w-0 flex-1" style={{ background: PHASE_COLOR[w.phase] ?? "#34343a", opacity: 0.85 }} title={`Week of ${formatDate(w.week)}: ${w.label}. ${w.blurb}`} />
        ))}
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-dim">
        {phases.map(([k, label]) => <span key={k}><span className="mr-1 inline-block h-2 w-2" style={{ background: PHASE_COLOR[k] }} />{label}</span>)}
      </p>
    </div>
  );
}

// ---- create / edit --------------------------------------------------------------------------

function GoalDialog({ target, onClose }: { target: GoalView | "new" | null; onClose: () => void }) {
  const open = target !== null;
  const edit = target && target !== "new" ? target : null;
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="surface fixed top-1/2 left-1/2 z-50 max-h-[92dvh] w-[min(94vw,520px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto p-6 sm:p-8" aria-describedby={undefined}>
          <Dialog.Close className="absolute top-4 right-4 p-1 text-mute hover:text-paper" aria-label="Close"><X size={18} /></Dialog.Close>
          <Dialog.Title className="font-display text-4xl text-cream">{edit ? "Edit goal" : "New goal"}</Dialog.Title>
          {open && <GoalForm key={edit?.id ?? "new"} edit={edit} onDone={onClose} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function GoalForm({ edit, onDone }: { edit: GoalView | null; onDone: () => void }) {
  const m = useGoalMutations();
  const [kind, setKind] = useState<GoalKind>(edit?.kind ?? "race");
  const [sport, setSport] = useState<GoalSport>(edit?.sport ?? "run");
  const initialM = edit?.spec.distance_m;
  const [metres, setMetres] = useState<number | "custom">(initialM && PRESETS[edit?.sport ?? "run"].some((p) => p.m === initialM) ? initialM : initialM ? "custom" : PRESETS.run[2].m);
  const [custom, setCustom] = useState(initialM && !PRESETS[edit?.sport ?? "run"].some((p) => p.m === initialM) ? String(+(initialM / 1000).toFixed(3)) : "");
  const [date, setDate] = useState(edit?.date ?? "");
  const [time, setTime] = useState(edit?.spec.target_s ? hms(edit.spec.target_s) : "");
  const [speed, setSpeed] = useState("");
  const [kg, setKg] = useState(edit?.spec.target_kg ? String(edit.spec.target_kg) : "");
  const [title, setTitle] = useState(edit && edit.title ? edit.title : "");
  const today = new Date().toISOString().slice(0, 10);

  const distance = metres === "custom" ? Number(custom) * 1000 : metres;
  const t = time.trim() ? parseTime(time) : null;
  const timeOk = !time.trim() || (t != null && t >= 60);
  const speedNum = speed.trim() ? Number(speed) : null;
  const speedOk = speedNum == null || (Number.isFinite(speedNum) && speedNum > 0 && speedNum <= 100);
  const weight = kind === "weight";
  const needsTarget = kind === "performance";
  const hasTarget = t != null || speedNum != null;
  const dateOk = kind === "race" ? date >= today : !date || date >= today;
  const valid = dateOk && (weight ? Number(kg) >= 30 && Number(kg) <= 300 : Number.isFinite(distance) && distance > 0 && timeOk && speedOk && (!needsTarget || hasTarget));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    const body: GoalInput = weight
      ? { kind, target_kg: Number(kg), date: date || null, title: title.trim() || null }
      : { kind, sport, distance_m: distance, date: date || null, target_s: t, speed_kmh: t == null ? speedNum : null, title: title.trim() || null };
    const done = () => { m.refresh(); onDone(); };
    if (edit) {
      const { kind: _kind, sport: _sport, ...patch } = body;
      void _kind; void _sport;
      api.updateGoal(edit.id, patch).then(done, () => setFailed(true));
    } else {
      api.createGoal(body).then(done, (err: Error) => setFailed(err.message || true));
    }
  };
  const [failed, setFailed] = useState<string | boolean>(false);
  const field = "num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-2xl text-paper outline-none focus:border-gold";
  return (
    <form onSubmit={submit} className="mt-6 space-y-6">
      {!edit && (
        <div>
          <p className="eyebrow mb-2">Type</p>
          <Segmented label="Goal type" options={(Object.keys(KIND_LABEL) as GoalKind[]).map((k) => ({ value: k, label: KIND_LABEL[k] }))} value={kind} onChange={setKind} />
          <p className="mt-2 text-xs text-dim">{KIND_HELP[kind]}</p>
        </div>
      )}
      {!weight && (
        <>
          {!edit && (
            <div>
              <p className="eyebrow mb-2">Sport</p>
              <Segmented label="Sport" options={[{ value: "run", label: "Run" }, { value: "ride", label: "Ride" }, { value: "swim", label: "Swim" }]} value={sport}
                onChange={(s) => { setSport(s); setMetres(PRESETS[s][1].m); }} />
            </div>
          )}
          <div>
            <p className="eyebrow mb-2">Distance</p>
            <div className="flex flex-wrap gap-2">
              {PRESETS[sport].map((p) => (
                <button key={p.m} type="button" aria-pressed={metres === p.m} onClick={() => setMetres(p.m)}
                  className={clsx("border px-3 py-1.5 text-xs font-semibold tracking-widest uppercase", metres === p.m ? "border-gold bg-gold/10 text-paper" : "border-line-strong text-mute hover:text-paper")}>{p.label}</button>
              ))}
              <button type="button" aria-pressed={metres === "custom"} onClick={() => setMetres("custom")}
                className={clsx("border px-3 py-1.5 text-xs font-semibold tracking-widest uppercase", metres === "custom" ? "border-gold bg-gold/10 text-paper" : "border-line-strong text-mute hover:text-paper")}>Other</button>
            </div>
            {metres === "custom" && <input aria-label="Distance in kilometres" inputMode="decimal" placeholder="km, e.g. 12.5" value={custom} onChange={(e) => setCustom(e.target.value)} className={field} />}
          </div>
          {kind !== "distance" && (
            <div className="grid grid-cols-2 gap-5">
              <div>
                <label className="eyebrow" htmlFor="goal-time">Target time{kind === "race" ? " (optional)" : ""}</label>
                <input id="goal-time" inputMode="numeric" placeholder="1:45:00" value={time} onChange={(e) => setTime(e.target.value)} aria-invalid={!timeOk} className={field} />
                {!timeOk && <p className="mt-1 text-xs text-coral">Use h:mm:ss or mm:ss.</p>}
              </div>
              <div>
                <label className="eyebrow" htmlFor="goal-speed">or average km/h</label>
                <input id="goal-speed" inputMode="decimal" placeholder="30" value={speed} onChange={(e) => setSpeed(e.target.value)} disabled={t != null} aria-invalid={!speedOk} className={clsx(field, t != null && "opacity-40")} />
              </div>
            </div>
          )}
        </>
      )}
      {weight && (
        <div>
          <label className="eyebrow" htmlFor="goal-kg">Target weight (kg)</label>
          <input id="goal-kg" inputMode="decimal" placeholder="72" value={kg} onChange={(e) => setKg(e.target.value)} className={field} />
        </div>
      )}
      <div>
        <label className="eyebrow" htmlFor="goal-date">{kind === "race" ? "Race date" : "Date (optional)"}</label>
        <input id="goal-date" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} className={field} />
      </div>
      <div>
        <label className="eyebrow" htmlFor="goal-title">Name (optional)</label>
        <input id="goal-title" maxLength={120} placeholder="Chosen for you" value={title} onChange={(e) => setTitle(e.target.value)} className="mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-lg text-paper outline-none focus:border-gold" />
      </div>
      {failed && <p role="alert" className="text-xs text-coral">{typeof failed === "string" ? failed : "Couldn't save. Try again."}</p>}
      <div className="flex flex-wrap gap-5">
        <button type="submit" className="pop pop-lime" disabled={!valid}><Route size={16} /> {edit ? "Save changes" : "Add goal"}</button>
      </div>
    </form>
  );
}
