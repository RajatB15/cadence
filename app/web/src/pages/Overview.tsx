import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  ArrowUpRight,
  BedDouble,
  CalendarCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Compass,
  Dumbbell,
  Flame,
  Mountain,
  Plane,
  Scale,
  Sun,
  TrendingUp,
  Utensils,
  Wind,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PhaseBanner } from "../components/PhaseBanner";
import { CheckInCard } from "../components/Journal";
import { TodayReadCard } from "../components/Reading";
import { Ring, SEVERITY, VerdictChip, readyColor } from "../components/CoachNotes";
import { CountUp } from "../components/CountUp";
import { RefreshChip } from "../components/RefreshButton";
import { EmptyState } from "../components/EmptyState";
import { WhatIfCard } from "../components/WhatIfCard";
import { RecoveryWinsCard, WellbeingCard } from "../components/Wellbeing";
import { Sheet } from "../components/Sheet";
import { TimeOffPanel } from "../components/TimeOff";
import { StatusPanel, TrendPanel } from "../components/Trends";
import { KIND_LABEL, STATUS_STYLE } from "../lib/trends";
import { DemoChip, ErrorBlock, LoadingBlock } from "../components/Shell";
import { Sparkline } from "../components/Sparkline";
import { api } from "../lib/api";
import { deltaTone, formatDelta, formatDuration, formatMetric, formatShortDate, formatWeekday, greeting } from "../lib/format";
import { METRIC_STYLES, activityStyle, fallbackStyle } from "../lib/metrics";
import type { Brief, MetricSummary, Overview, ReadinessComponent, ScoreSummary } from "../lib/types";

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
};
const rise = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.2, 0.9, 0.1, 1] as const } },
};

export function OverviewPage() {
  // Live readiness moves through the day; keep Home current while it's open.
  const query = useQuery({ queryKey: ["overview"], queryFn: api.overview, refetchInterval: 5 * 60_000 });
  if (query.isPending) return <LoadingBlock height={520} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  if (!query.data.has_data) return <EmptyState />;
  return <Dashboard data={query.data} />;
}

// Steps and load swing with the training schedule, so they make poor headlines.
const HEADLINE_METRICS = new Set(["hrv", "resting_hr", "sleep_hours", "body_battery", "stress"]);

function headline(metrics: MetricSummary[]): { text: string; tone: string } {
  const ranked = metrics
    .filter((m) => HEADLINE_METRICS.has(m.metric) && m.delta_pct != null && m.higher_is_better != null)
    .sort((a, b) => Math.abs(b.delta_pct!) - Math.abs(a.delta_pct!));
  const top = ranked[0];
  if (!top) {
    return { text: "Your Garmin history starts here.", tone: "text-cream" };
  }
  if (Math.abs(top.delta_pct!) < 3) {
    return { text: "Everything is holding close to your baseline.", tone: "text-cream" };
  }
  const dir = top.delta_pct! > 0 ? "above" : "below";
  const tone = deltaTone(top.delta_pct, top.higher_is_better) === "good" ? "text-lime" : "text-amber";
  return {
    text: `${top.label} is running ${Math.abs(top.delta_pct!).toFixed(1)}% ${dir} your baseline.`,
    tone,
  };
}

function Dashboard({ data }: { data: Extract<Overview, { has_data: true }> }) {
  const now = new Date();
  const coach = data.coach;
  const isDemo = data.source_id === "demo";
  const wide = useWide();
  const [sheet, setSheet] = useState<null | "readiness" | "score" | "week" | "status" | "timeoff">(null);
  const r = coach?.readiness;
  const fallback = headline(data.metrics);
  const [params] = useSearchParams();

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-10">
      <motion.section variants={rise}>
        <div className="eyebrow mb-4 flex flex-wrap items-center gap-3">
          <span>{formatWeekday(toDay(now))}</span>
          {isDemo ? <DemoChip /> : <RefreshChip />}
        </div>
        <h1 className="font-display text-5xl leading-[0.95] tracking-tight text-cream sm:text-7xl">{greeting(now.getHours())}.</h1>
        {!r && <p className={clsx("mt-4 font-display text-2xl italic", fallback.tone)}>{fallback.text}</p>}
      </motion.section>

      <motion.div variants={rise}><PhaseBanner /></motion.div>

      {(r || data.score) && (
        <motion.section variants={rise} aria-label="Scores" className="grid grid-cols-2 gap-3 sm:gap-4">
          {r && coach?.call && (
            <Dial
              label="Readiness"
              score={r.score}
              ring={r.live ? "live" : "today"}
              size={wide ? 190 : 128}
              title={coach.call.headline}
              foot={r.live && r.morning_score != null && r.morning_score !== r.score ? `${r.morning_score} this morning` : "Updates through the day"}
              onClick={() => setSheet("readiness")}
            />
          )}
          {data.score && (
            <Dial
              label="Cadence score"
              score={data.score.score}
              ring="cadence"
              size={wide ? 190 : 128}
              title={data.score.label}
              foot={data.score.delta_7d != null ? `${data.score.delta_7d >= 0 ? "+" : "−"}${Math.abs(data.score.delta_7d)} vs last week` : "Train · Recover · Sleep · Move"}
              onClick={() => setSheet("score")}
            />
          )}
        </motion.section>
      )}

      {coach && <StatusCard coach={coach} onStatus={() => setSheet("status")} onTimeOff={() => setSheet("timeoff")} />}

      {data.journal && (
        <motion.section variants={rise}>
          <CheckInCard day={data.journal.day} done={data.journal.done} count={data.journal.behaviours.length} autoOpen={params.get("checkin") === "1"} />
        </motion.section>
      )}

      <motion.section variants={rise}><TodayReadCard /></motion.section>

      {coach && <motion.section variants={rise}><WellbeingCard day={data.today} block={coach.wellbeing} /></motion.section>}

      <ReviewPrompt />

      <motion.section variants={rise} className="flex flex-wrap gap-3">
        {!data.weight.weighed_today && (
          <Link to="/weight?log=1" className="chip text-mute hover:text-paper pointer-coarse:py-2">
            <Scale size={12} className="text-gold" /> Log weight
          </Link>
        )}
        <Link to="/food" className="chip text-mute hover:text-paper pointer-coarse:py-2">
          <Utensils size={12} className="text-gold" /> Log food
        </Link>
        <Link to="/phases" className="chip text-mute hover:text-paper pointer-coarse:py-2">
          <Flame size={12} className="text-gold" /> Phases
        </Link>
      </motion.section>

      <PlannedToday plans={data.planned_today ?? []} />

      {coach && <TodayCall coach={coach} />}

      {coach?.strain && <StrainRow s={coach.strain} />}

      {coach?.weather && (coach.weather.hot || coach.weather.better_hour != null) && <WeatherRow w={coach.weather} />}

      {coach?.tonight && <TonightRow t={coach.tonight} />}

      {coach && coach.recent.items.length > 0 && <RecentSessions recent={coach.recent} />}

      {coach && <WhatIfCard card={coach.what_if} />}

      {coach && coach.week.items.length > 0 && <WeekStrip coach={coach} onOpen={() => setSheet("week")} />}

      {data.score && data.score.top_gaps.length > 0 && <BiggestGain gap={data.score.top_gaps[0]} />}

      <VitalsStrip data={data} />

      {coach && coach.streaks.length > 0 && <StreakChips streaks={coach.streaks} />}

      {coach && <RecoveryWinsCard wins={coach.recovery_wins} />}

      {coach && r && (
        <Sheet open={sheet === "readiness"} onOpenChange={(o) => setSheet(o ? "readiness" : null)} title="Readiness" eyebrow={r.live ? "Live · updates through the day" : "This morning"}>
          <ReadinessDetail coach={coach} />
        </Sheet>
      )}
      {data.score && (
        <Sheet open={sheet === "score"} onOpenChange={(o) => setSheet(o ? "score" : null)} title="Cadence score" eyebrow={`${data.score.score} today · ${data.score.label}`}>
          <ScoreDetail score={data.score} />
        </Sheet>
      )}
      {coach && (
        <Sheet open={sheet === "status"} onOpenChange={(o) => setSheet(o ? "status" : null)} title="Training status" eyebrow="Progressing, maintaining, overloading, deloading">
          <StatusPanel />
        </Sheet>
      )}
      <Sheet open={sheet === "timeoff"} onOpenChange={(o) => setSheet(o ? "timeoff" : null)} title="Time off & ramp" eyebrow="Travel · holiday · illness · injury">
        <TimeOffPanel />
      </Sheet>
      {coach && (
        <Sheet open={sheet === "week"} onOpenChange={(o) => setSheet(o ? "week" : null)} title="This week vs plan" eyebrow={coach.focus ? `Focus: ${coach.focus}` : undefined}>
          <WeekTargets coach={coach} bare />
        </Sheet>
      )}
    </motion.div>
  );
}

function useWide(): boolean {
  const query = "(min-width: 640px)";
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setWide(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return wide;
}

// ---- headline dials --------------------------------------------------------------------

function Dial({ label, score, ring, size, title, foot, onClick, to }: {
  label: string; score: number; ring: string; size: number; title: string; foot: string; onClick?: () => void; to?: string;
}) {
  const body = (
    <div className="surface surface-hover group relative flex h-full flex-col items-center overflow-hidden px-3 py-5 text-center sm:p-7">
      <p className="eyebrow mb-3 sm:mb-5">{label}</p>
      <Ring score={score} size={size} label={ring} />
      <p className="mt-3 font-display text-xl leading-tight text-cream sm:mt-5 sm:text-3xl">{title}</p>
      <p className="mt-1 text-[11px] text-mute sm:text-xs">{foot}</p>
      <span className="eyebrow mt-3 flex items-center gap-1 !text-[10px] opacity-60 transition-opacity group-hover:opacity-100">
        Why <ChevronRight size={10} />
      </span>
    </div>
  );
  return to ? (
    <Link to={to} aria-label={`${label} details`}>{body}</Link>
  ) : (
    <button type="button" onClick={onClick} aria-label={`${label} details`} className="block w-full text-left">
      {body}
    </button>
  );
}

const READINESS_VALUE: Record<string, (c: ReadinessComponent) => string> = {
  sleep: (c) => (c.value != null ? `score ${c.value}` : `${c.hours?.toFixed(1)} h`),
  sleep_history: (c) => `${c.value} h avg`,
  hrv: (c) => (c.range ? `${c.value} ms · range ${c.range[0]}–${c.range[1]}` : `${c.value} ms`),
  rhr: (c) => `${c.value} bpm · ${c.delta != null && c.delta >= 0 ? "+" : ""}${c.delta} vs normal`,
  load: (c) => `ratio ${c.acwr?.toFixed(2) ?? "—"}${c.strain ? ` · −${c.strain} from today` : ""}`,
  battery: (c) => (c.now != null ? `${c.now} now · peak ${c.peak}` : `${c.value}`),
};

function ScoreDetail({ score }: { score: NonNullable<Extract<Overview, { has_data: true }>["score"]> }) {
  return (
    <div className="space-y-8">
      <TrendPanel kind="score" title="Cadence score" />
      <div>
        <p className="eyebrow mb-3">Today by pillar</p>
        <ul className="space-y-2 text-sm">
          {score.groups.map((g) => (
            <li key={g.key} className="flex justify-between gap-3"><span className="text-mute">{g.label}</span><span className="num" style={{ color: readyColor(g.score) }}>{g.score}</span></li>
          ))}
        </ul>
      </div>
      <Link to="/score" className="chip text-paper pointer-coarse:py-2">Full breakdown and every factor <ChevronRight size={12} /></Link>
    </div>
  );
}

function ReadinessDetail({ coach }: { coach: Brief }) {
  const r = coach.readiness!;
  return (
    <div className="space-y-8">
      <div className="flex items-center gap-6">
        <Ring score={r.score} size={130} label={r.live ? "live" : "today"} />
        <div>
          <p className="font-display text-3xl text-cream">{coach.call?.headline}</p>
          <p className="mt-2 text-sm text-mute">{coach.call?.detail}</p>
        </div>
      </div>
      <TrendPanel kind="readiness" title="Readiness" />
      {r.live && r.morning_score != null && (
        <div>
          <p className="eyebrow mb-3">Since this morning</p>
          <div className="flex items-baseline gap-3">
            <span className="num text-2xl text-mute">{r.morning_score}</span>
            <ArrowUpRight size={14} className={clsx(r.score < r.morning_score && "rotate-90", "text-dim")} />
            <span className="num text-2xl" style={{ color: readyColor(r.score) }}>{r.score}</span>
          </div>
          {r.changes && r.changes.length > 0 ? (
            <ul className="mt-3 space-y-1.5 text-sm">
              {r.changes.map((c) => (
                <li key={c.label} className="flex justify-between gap-3">
                  <span className="text-mute">{c.label}</span>
                  <span className={clsx("num", c.delta < 0 ? "text-coral" : "text-lime")}>{c.delta > 0 ? "+" : ""}{c.delta}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-dim">No change yet. Training and Body Battery drain will move it through the day.</p>
          )}
        </div>
      )}
      <div>
        <p className="eyebrow mb-4">What goes into it</p>
        <ul className="space-y-4">
          {Object.entries(r.components).map(([key, c], i) => (
            <li key={key}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="text-paper">{COMPONENT_LABEL[key] ?? key} <span className="text-[10px] text-dim">· {Math.round(c.weight * 100)}%</span></span>
                <span className="num text-mute">{READINESS_VALUE[key]?.(c)}</span>
              </div>
              <div className="mt-1.5 flex items-center gap-3">
                <div className="h-1.5 flex-1 bg-slate">
                  <motion.div
                    className="h-full"
                    style={{ background: readyColor(c.score) }}
                    initial={{ width: 0 }}
                    whileInView={{ width: `${c.score}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.9, delay: i * 0.06 }}
                  />
                </div>
                <span className="num w-7 text-right text-xs text-paper">{c.score}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>
      {coach.readiness_trend.length > 3 && (
        <div>
          <p className="eyebrow mb-2">Morning readiness · 14 days</p>
          <Sparkline values={coach.readiness_trend.map((t) => t.score)} color={readyColor(r.score)} height={56} />
        </div>
      )}
      <Link to="/coach" className="eyebrow inline-flex items-center gap-1 hover:text-paper">
        Full coach view <ArrowUpRight size={11} />
      </Link>
    </div>
  );
}

// ---- today's call -----------------------------------------------------------------------

function TodayCall({ coach }: { coach: Brief }) {
  const [open, setOpen] = useState(false);
  const t = coach.today;
  const k = TODAY_KIND[t.kind];
  const Icon = k.icon;
  const status = t.status ? STATUS[t.status] : null;
  const color = status?.color ?? k.color;
  const hasMore = t.kind === "done" || Boolean(coach.call?.detail);
  return (
    <motion.section variants={rise} aria-label="Today" className="surface relative overflow-hidden p-5 sm:p-7">
      <div className="pointer-events-none absolute -top-20 -right-12 h-56 w-56 rounded-full opacity-15 blur-3xl" style={{ background: color }} />
      <div className="flex items-start gap-4">
        <div className="grid h-11 w-11 shrink-0 place-items-center" style={{ background: `${color}1f`, color }}>
          <Icon size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="eyebrow mb-1" style={{ color }}>Today · {status?.label ?? k.label}</p>
          <h2 className="font-display text-3xl leading-tight text-cream sm:text-4xl">{t.title}</h2>
          <p className="mt-2 text-mute">{t.kind === "done" ? t.next : t.detail}</p>
          {coach.call?.source === "check-in" && <p className="mt-2 text-xs font-semibold tracking-widest text-gold uppercase">From your check-in</p>}
        </div>
      </div>
      {hasMore && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="eyebrow mt-4 ml-15 flex items-center gap-1 hover:text-paper"
        >
          {open ? "Less" : "Why & details"}
          <ChevronDown size={12} className={clsx("transition-transform", open && "rotate-180")} />
        </button>
      )}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.2, 0.9, 0.1, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-4 grid gap-3 sm:ml-15 sm:grid-cols-2">
              {t.kind === "done" && <p className="text-sm text-mute sm:col-span-2">{t.detail}</p>}
              {t.planned && (
                <div className="border border-line bg-ink/40 p-4">
                  <p className="eyebrow mb-1">Today called for</p>
                  <p className="text-paper">{t.planned}</p>
                </div>
              )}
              {coach.call && (
                <div className="border border-line bg-ink/40 p-4">
                  <p className="eyebrow mb-1">Readiness says</p>
                  <p className="text-sm text-paper">{coach.call.detail}</p>
                </div>
              )}
              {t.second && (
                <div className="border border-dashed border-lime/40 p-4 sm:col-span-2">
                  <p className="text-sm font-semibold text-lime">{t.second.title}</p>
                  <p className="mt-1 text-sm text-mute">{t.second.detail}</p>
                </div>
              )}
              {coach.focus && (
                <p className="text-xs text-dim sm:col-span-2">
                  Week focus: {coach.focus}
                  {coach.goal && coach.phase?.weeks_to_race != null && ` · ${coach.phase.weeks_to_race} weeks to your ${coach.goal.label.toLowerCase()}`}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

// ---- week at a glance -------------------------------------------------------------------

const WEEK_SHORT: Record<string, string> = {
  load: "Load", sessions: "Sessions", hard: "Quality", long: "Long run", easy: "Kept easy", sleep: "Full nights", strength: "Strength", bed: "By 23:30",
};

function StatusCard({ coach, onStatus, onTimeOff }: { coach: Brief; onStatus: () => void; onTimeOff: () => void }) {
  const off = coach.week.time_off;
  const st = coach.status;
  const color = STATUS_STYLE[st.status].color;
  const q = useQuery({ queryKey: ["time-off"], queryFn: api.timeOff });
  const today = q.data?.today ?? coach.as_of;
  const soon = new Date(`${today}T00:00:00`);
  soon.setDate(soon.getDate() + 14);
  const horizon = toDay(soon);
  const entries = (q.data?.items ?? []).filter((i) => (!i.end || i.end >= today) && i.start <= horizon);
  return (
    <motion.section variants={rise} aria-label="Training status" className="surface p-5 sm:p-6" style={{ borderLeft: `3px solid ${color}` }}>
      <button type="button" onClick={onStatus} className="group block w-full text-left" aria-label={`Training status: ${st.label}. Show the weekly history`}>
        <div className="flex items-center justify-between gap-3">
          <p className="font-display text-3xl leading-tight sm:text-4xl" style={{ color }}>{st.label}</p>
          <ChevronRight size={16} className="shrink-0 text-dim group-hover:text-paper" />
        </div>
        <p className="mt-1 text-sm text-mute">{st.why}</p>
      </button>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {entries.map((i) => (
          <button key={i.id} type="button" onClick={onTimeOff} className="chip text-paper pointer-coarse:py-2">
            <Plane size={12} className="text-gold" />
            {KIND_LABEL[i.kind]} · {i.ongoing ? "ongoing" : i.start > today ? formatShortDate(i.start) : `to ${formatShortDate(i.end!)}`}
          </button>
        ))}
        {off && <span className="num text-xs text-mute">{Math.round(off.scale * 100)}% targets · no miss</span>}
        <button type="button" onClick={onTimeOff} className="chip text-mute hover:text-paper pointer-coarse:py-2">
          <Plane size={12} className="text-gold" /> Away or ill?
        </button>
      </div>
    </motion.section>
  );
}

function MiniRing({ done, target, low }: { done: number; target: number; low?: number }) {
  const goal = low ?? target;
  const pct = Math.min(1, done / Math.max(1, target));
  const color = low != null && done > target ? "#ffbe55" : done >= goal ? "#c8f560" : "#d9b26a";
  const r = 22;
  const circ = 2 * Math.PI * r;
  return (
    <div className="relative h-14 w-14">
      <svg viewBox="0 0 52 52" className="h-full w-full -rotate-90">
        <circle cx="26" cy="26" r={r} fill="none" stroke="#1c1c1f" strokeWidth="4" />
        <motion.circle
          cx="26" cy="26" r={r} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          whileInView={{ strokeDashoffset: circ * (1 - pct) }}
          viewport={{ once: true }}
          transition={{ duration: 1.1, ease: [0.2, 0.9, 0.1, 1] }}
        />
      </svg>
      <span className="num absolute inset-0 grid place-items-center text-xs text-paper">{done >= goal ? <CheckCircle2 size={16} className="text-lime" /> : done}</span>
    </div>
  );
}

function WeekStrip({ coach, onOpen }: { coach: Brief; onOpen: () => void }) {
  const w = coach.week;
  const hit = w.items.filter((i) => i.done >= (i.low ?? i.target)).length;
  return (
    <motion.section variants={rise}>
      <button type="button" onClick={onOpen} className="surface surface-hover group block w-full p-5 text-left sm:p-6">
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <p className="eyebrow">This week · {hit}/{w.items.length} on target</p>
          <span className="eyebrow flex items-center gap-1 text-gold group-hover:text-paper">
            {w.days_left === 0 ? "Last day" : `${w.days_left} day${w.days_left === 1 ? "" : "s"} left`} <ChevronRight size={11} />
          </span>
        </div>
        <div className="grid grid-cols-3 gap-x-2 gap-y-4 sm:flex sm:gap-6 sm:overflow-x-auto sm:pb-1">
          {w.items.map((item) => (
            <div key={item.key} className="flex flex-col items-center text-center sm:w-16 sm:shrink-0">
              <MiniRing done={item.done} target={item.target} low={item.low} />
              <p className="mt-2 text-[10px] leading-tight tracking-wide text-mute uppercase">{WEEK_SHORT[item.key] ?? item.label}</p>
              <p className="num text-[11px] text-dim">{item.done}/{item.low ?? item.target}</p>
            </div>
          ))}
        </div>
      </button>
    </motion.section>
  );
}

const hhmm = (m: number) => {
  const v = ((Math.round(m) % 1440) + 1440) % 1440;
  return `${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`;
};

/** Early in a new week (or Sunday evening) and early in a month, point at the fresh review. */
function ReviewPrompt() {
  const now = new Date();
  const day = now.getDay(); // 0 = Sunday
  const weekly = (day === 0 && now.getHours() >= 18) || day === 1 || day === 2;
  const monthly = now.getDate() <= 3;
  if (!weekly && !monthly) return null;
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((day + 6) % 7) - (day === 0 ? 0 : 7));
  const to = monthly && !weekly ? "/review?kind=month" : day === 0 ? `/review?kind=week&start=${toDay(monday)}` : "/review";
  return (
    <motion.section variants={rise}>
      <Link to={to} className="chip text-mute hover:text-paper pointer-coarse:py-2">
        <TrendingUp size={12} className="text-gold" /> {monthly && !weekly ? "Your month in review" : "Your week in review"}
      </Link>
    </motion.section>
  );
}

function PlannedToday({ plans }: { plans: NonNullable<Extract<Overview, { has_data: true }>["planned_today"]> }) {
  if (!plans.length) {
    return (
      <motion.section variants={rise}>
        <Link to="/plan" className="chip text-mute hover:text-paper pointer-coarse:py-2">
          <CalendarCheck size={12} className="text-gold" /> Plan today's session and see what it will do
        </Link>
      </motion.section>
    );
  }
  return (
    <motion.section variants={rise} className="space-y-3">
      {plans.map((p) => (
        <Link key={p.id} to={p.activity ? `/activities/${p.activity.id}` : "/plan"} className="surface surface-hover flex items-center gap-4 p-5"
          style={{ borderLeft: `3px solid ${p.status === "done" ? "#c8f560" : "#d9b26a"}` }}>
          <CalendarCheck size={20} className={clsx("shrink-0", p.status === "done" ? "text-lime" : "text-gold")} />
          <div className="min-w-0 flex-1">
            <p className="eyebrow mb-0.5">{p.status === "done" ? "Planned · done" : "Planned today"}</p>
            <p className="truncate text-paper">{p.title}</p>
            <p className="text-xs text-dim">
              Predicted load {p.predicted.load}
              {p.activity?.load != null ? ` · actual ${Math.round(p.activity.load)}` : p.predicted.recovery_days ? ` · recovered in ~${p.predicted.recovery_days} d` : ""}
            </p>
          </div>
          <ChevronRight size={16} className="shrink-0 text-dim" />
        </Link>
      ))}
    </motion.section>
  );
}

function StrainRow({ s }: { s: NonNullable<Brief["strain"]> }) {
  const b = s.band;
  const top = Math.max(b ? b.high * 1.35 : 0, s.total * 1.1, 1);
  const pct = (v: number) => `${Math.min(100, (v / top) * 100)}%`;
  const color = s.status === "above" ? "#ffbe55" : s.status === "in" ? "#c8f560" : "#6cc7ff";
  return (
    <motion.section variants={rise} className="surface p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="eyebrow">Strain today</p>
        <p className="num text-2xl" style={{ color }}>{Math.round(s.total)}{b && <span className="text-sm text-dim"> / {b.low}–{b.high}</span>}</p>
      </div>
      <div className="relative mt-3 h-2.5 bg-slate" role="img" aria-label={b ? `Strain ${Math.round(s.total)}, target ${b.low} to ${b.high}` : `Strain ${Math.round(s.total)}`}>
        {b && <div className="absolute inset-y-0 bg-lime/15 outline outline-1 outline-lime/40" style={{ left: pct(b.low), width: `calc(${pct(b.high)} - ${pct(b.low)})` }} />}
        <motion.div className="absolute inset-y-0 left-0" style={{ background: color }} initial={{ width: 0 }} animate={{ width: pct(s.total) }} transition={{ duration: 0.9 }} />
      </div>
      <p className="mt-2 text-xs text-dim">
        {Math.round(s.workout)} from workouts · {Math.round(s.everyday)} from everyday movement{s.message ? ` · ${s.message}` : ""}
        {!s.calibrated && " (rough units until 10 workouts calibrate it)"}
      </p>
    </motion.section>
  );
}

function WeatherRow({ w }: { w: NonNullable<Brief["weather"]> }) {
  const h = (n: number) => `${String(n).padStart(2, "0")}:00`;
  return (
    <motion.section variants={rise} className="surface flex items-center gap-4 p-5" style={{ borderLeft: "3px solid #ffbe55" }}>
      <Sun size={20} className="shrink-0 text-amber" />
      <div className="min-w-0 flex-1">
        <p className="eyebrow mb-0.5">Heat today</p>
        <p className="text-paper">
          {w.temperature?.toFixed(0)} °C, dew point {w.dew_point?.toFixed(0)} °C at {h(w.hour)}: about {w.cost_pct.toFixed(0)}% slower at the same effort
        </p>
        {w.better_hour != null && <p className="text-xs text-dim">At {h(w.better_hour)} it's about {w.better_cost_pct!.toFixed(0)}%: go then if you can, or run by effort.</p>}
      </div>
    </motion.section>
  );
}

function TonightRow({ t }: { t: NonNullable<Brief["tonight"]> }) {
  const extras = [t.extra_load_min ? `+${t.extra_load_min} min for today's training` : null, t.repay_min ? `+${t.repay_min} min toward ${t.debt_h} h of debt` : null].filter(Boolean);
  return (
    <motion.section variants={rise}>
      <Link to="/coach#sleep" className="surface surface-hover group flex items-center gap-4 p-5" style={{ borderLeft: "3px solid #6cc7ff" }}>
        <BedDouble size={20} className="shrink-0 text-sky" />
        <div className="min-w-0 flex-1">
          <p className="eyebrow mb-0.5">Tonight</p>
          <p className="text-paper">
            In bed by <span className="num text-sky">{hhmm(t.bed_min)}</span> · {t.tonight_h.toFixed(1)} h to wake at {hhmm(t.wake_min)}
          </p>
          {t.capped ? (
            <p className="text-xs text-dim">An hour earlier than usual; keep stepping toward {t.ideal_h.toFixed(1)} h over the week.</p>
          ) : (
            extras.length > 0 && <p className="text-xs text-dim">Your {t.need_h} h need {extras.join(", ")}</p>
          )}
        </div>
        <ChevronRight size={16} className="shrink-0 text-dim transition-transform group-hover:translate-x-0.5" />
      </Link>
    </motion.section>
  );
}

function BiggestGain({ gap }: { gap: ScoreSummary["top_gaps"][number] }) {
  return (
    <motion.section variants={rise}>
      <Link to="/score" className="surface surface-hover group flex items-center gap-4 p-5" style={{ borderLeft: "3px solid #ffbe55" }}>
        <TrendingUp size={20} className="shrink-0 text-amber" />
        <div className="min-w-0 flex-1">
          <p className="eyebrow mb-0.5">Biggest gain available</p>
          <p className="line-clamp-2 text-paper">
            {gap.label} <span className="text-mute">· {gap.value} → {gap.target}</span>
          </p>
        </div>
        <span className="num shrink-0 text-lg text-amber">+{gap.points_lost.toFixed(1)}</span>
        <ChevronRight size={16} className="shrink-0 text-dim transition-transform group-hover:translate-x-0.5" />
      </Link>
    </motion.section>
  );
}

// ---- vitals strip -----------------------------------------------------------------------

function VitalsStrip({ data }: { data: Extract<Overview, { has_data: true }> }) {
  const w = data.weight;
  return (
    <motion.section variants={rise} aria-label="Vitals">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="eyebrow">Vitals · 7-day vs 60-day</p>
        <p className="eyebrow !text-dim">Tap to explore</p>
      </div>
      <div className="-mx-5 flex snap-x gap-3 overflow-x-auto px-5 pb-2 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 lg:grid-cols-5">
        {data.metrics.map((m) => (
          <VitalTile key={m.metric} m={m} />
        ))}
        {w.latest_trend_kg != null && (
          <Link to="/weight" className="surface surface-hover flex w-40 shrink-0 snap-start flex-col p-4 sm:w-auto">
            <span className="eyebrow flex items-center gap-1.5 !text-[10px]"><Scale size={12} className="text-gold" /> Weight</span>
            <span className="num mt-3 text-2xl text-paper">{(w.latest_reading?.weight_kg ?? w.latest_trend_kg).toFixed(1)}<span className="ml-1 text-xs text-mute">kg</span></span>
            {w.latest_reading && <span className="mt-0.5 text-[11px] text-dim">last weigh-in · trend {w.latest_trend_kg.toFixed(1)}</span>}
            <Sparkline values={w.spark.map((s) => s.value)} color="#d9b26a" height={28} className="mt-auto pt-2" />
          </Link>
        )}
      </div>
    </motion.section>
  );
}

function VitalTile({ m }: { m: MetricSummary }) {
  const style = METRIC_STYLES[m.metric] ?? fallbackStyle;
  const Icon = style.icon;
  const tone = deltaTone(m.delta_pct, m.higher_is_better);
  const fmt = useCallback((v: number) => formatMetric(v, m.metric), [m.metric]);
  return (
    <Link to={`/metrics/${m.metric}`} className="surface surface-hover flex w-40 shrink-0 snap-start flex-col p-4 sm:w-auto">
      <span className="eyebrow flex items-center justify-between gap-1.5 !text-[10px]">
        <span className="flex items-center gap-1.5 truncate"><Icon size={12} style={{ color: style.color }} /> {m.label}</span>
        {m.delta_pct != null && (
          <span className={clsx("num shrink-0 normal-case", tone === "good" ? "text-lime" : tone === "bad" ? "text-amber" : "text-dim")}>
            {formatDelta(m.delta_pct)}
          </span>
        )}
      </span>
      <span className="mt-3 text-paper">
        <CountUp value={m.latest} format={fmt} className="num text-2xl" />
        <span className="ml-1 text-xs text-mute">{m.unit}</span>
      </span>
      <Sparkline values={m.spark.map((p) => p.value)} color={style.color} height={28} className="mt-auto pt-2" />
    </Link>
  );
}

function StreakChips({ streaks }: { streaks: Brief["streaks"] }) {
  return (
    <motion.section variants={rise} aria-label="Streaks" className="flex flex-wrap gap-2">
      {streaks.map((s) => {
        const record = s.current > 0 && s.current >= s.best;
        return (
          <span key={s.key} className={clsx("chip gap-1.5", record ? "!border-gold/50 !text-gold" : "")} title={`Best ${s.best} ${s.unit}`}>
            <Flame size={11} className={s.current > 0 ? "text-gold" : "text-dim"} />
            <span className="num">{s.current}</span> {s.label.toLowerCase()}
            {record ? " · best ever" : ` · best ${s.best}`}
          </span>
        );
      })}
    </motion.section>
  );
}

function toDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ---- coach brief ------------------------------------------------------------------

const TODAY_KIND: Record<Brief["today"]["kind"], { icon: typeof Flame; color: string; label: string }> = {
  key: { icon: Flame, color: "#d9b26a", label: "Quality day" },
  easy: { icon: Wind, color: "#5be3b0", label: "Easy day" },
  long: { icon: Mountain, color: "#6cc7ff", label: "Long day" },
  rest: { icon: BedDouble, color: "#9b8cff", label: "Recovery day" },
  strength: { icon: Dumbbell, color: "#ff6a55", label: "Strength day" },
  done: { icon: CheckCircle2, color: "#c8f560", label: "Done" },
  unknown: { icon: Compass, color: "#f2e8cf", label: "By feel" },
};
const COMPONENT_LABEL: Record<string, string> = {
  sleep: "Sleep", sleep_history: "Sleep history", hrv: "HRV", rhr: "Resting HR", load: "Load", battery: "Body Battery",
};
const STATUS: Record<NonNullable<Brief["today"]["status"]>, { label: string; color: string }> = {
  matched: { label: "Plan done", color: "#c8f560" },
  open: { label: "Still open", color: "#ffbe55" },
  over: { label: "Harder than planned", color: "#ff6a55" },
  extra: { label: "Bonus session", color: "#6cc7ff" },
};

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

function RecentSessions({ recent }: { recent: Brief["recent"] }) {
  return (
    <motion.section variants={rise} aria-label="Latest sessions">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-display text-3xl text-cream">{recent.label === "Today" ? "Today's sessions" : `${recent.label}'s sessions`}</h2>
        <Link to="/activities" className="eyebrow flex items-center gap-1 hover:text-paper">
          All activities <ArrowUpRight size={12} />
        </Link>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {recent.items.map((s) => {
          const style = activityStyle(s.type, s.family);
          const Icon = style.icon;
          const sev = s.note ? SEVERITY[s.note.severity] : null;
          return (
            <Link
              key={s.id}
              to={`/activities/${s.id}`}
              className="surface surface-hover group relative flex flex-col overflow-hidden p-5"
              style={{ borderTop: `2px solid ${style.color}` }}
            >
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center" style={{ background: `${style.color}1a`, color: style.color }}>
                  <Icon size={18} strokeWidth={1.75} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-paper">{s.name}</p>
                  <p className="text-xs text-mute">
                    {style.label}
                    {s.start && ` · ${timeFmt.format(new Date(s.start))}`}
                  </p>
                </div>
                {s.verdict && <VerdictChip v={s.verdict} />}
              </div>
              <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
                {[
                  s.moving_s ? { k: "time", v: formatDuration(s.moving_s) } : null,
                  s.distance_m ? { k: "km", v: (s.distance_m / 1000).toFixed(1) } : null,
                  s.avg_hr ? { k: "bpm", v: Math.round(s.avg_hr).toString() } : null,
                  { k: "load", v: s.load.toString() },
                ].filter((x): x is { k: string; v: string } => x !== null).map((x) => (
                  <div key={x.k}>
                    <dd className="num text-lg text-paper">{x.v}</dd>
                    <dt className="text-[10px] tracking-widest text-dim uppercase">{x.k}</dt>
                  </div>
                ))}
              </dl>
              {s.intensity && (
                <div className="mt-4 flex h-1.5 overflow-hidden" title={`Easy ${s.intensity.easy_pct}% · Z3 ${s.intensity.moderate_pct}% · Hard ${s.intensity.hard_pct}%`}>
                  <span style={{ width: `${s.intensity.easy_pct}%`, background: "#5be3b0" }} />
                  <span style={{ width: `${s.intensity.moderate_pct}%`, background: "#c8f560" }} />
                  <span style={{ width: `${s.intensity.hard_pct}%`, background: "#ff6a55" }} />
                </div>
              )}
              {s.note && sev && (
                <p className="mt-4 border-t border-line/60 pt-3 text-sm">
                  <span className="font-semibold" style={{ color: sev.color }}>{s.note.title}.</span>{" "}
                  <span className="line-clamp-2 text-mute">{s.note.detail}</span>
                </p>
              )}
              <p className="eyebrow mt-auto flex items-center gap-1 pt-4 group-hover:text-paper">
                Open analysis{s.notes > 1 ? ` · ${s.notes} notes` : ""} <ArrowUpRight size={11} />
              </p>
            </Link>
          );
        })}
      </div>
    </motion.section>
  );
}

function WeekTargets({ coach, bare = false }: { coach: Brief; bare?: boolean }) {
  const w = coach.week;
  const hit = w.items.filter((i) => i.done >= (i.low ?? i.target)).length;
  return (
    <div className={clsx(!bare && "surface p-6 sm:p-8")}>
      <div className="mb-6 flex items-baseline justify-between gap-3">
        <div>
          {!bare && <p className="eyebrow mb-2">This week vs plan</p>}
          <h2 className={clsx("font-display text-cream", bare ? "text-2xl" : "text-3xl")}>
            {hit} of {w.items.length} on target
          </h2>
        </div>
        <p className="num text-sm text-gold">
          {w.days_left === 0 ? "Last day" : `${w.days_left} day${w.days_left === 1 ? "" : "s"} left`}
        </p>
      </div>
      <ul className="space-y-5">
        {w.items.map((item, i) => {
          const goal = item.low ?? item.target;
          const done = item.done >= goal;
          const over = item.low != null && item.done > item.target;
          const color = over ? "#ffbe55" : done ? "#c8f560" : "#d9b26a";
          const pct = Math.min(100, (item.done / Math.max(1, item.target)) * 100);
          const togo = Math.max(0, goal - item.done);
          return (
            <li key={item.key}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                <span className="flex items-center gap-2 text-paper">
                  {done && !over && <CheckCircle2 size={14} className="text-lime" />}
                  {item.label}
                </span>
                <span className="num text-mute">
                  <span className="text-paper">{item.done}</span> / {item.low != null ? `${item.low}–${item.target}` : item.target}
                  {!done && togo > 0 && <span className="ml-2 text-gold">{togo} to go</span>}
                  {over && <span className="ml-2 text-amber">over band</span>}
                </span>
              </div>
              <div className="relative mt-2 h-1.5 bg-slate">
                {item.low != null && (
                  <span className="absolute inset-y-0 bg-lime/15" style={{ left: `${(item.low / item.target) * 100}%`, right: 0 }} />
                )}
                <motion.div
                  className="relative h-full"
                  style={{ background: color }}
                  initial={{ width: 0 }}
                  whileInView={{ width: `${pct}%` }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.9, delay: i * 0.05 }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
