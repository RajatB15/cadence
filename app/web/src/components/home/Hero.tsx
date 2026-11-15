import { clsx } from "clsx";
import { ArrowUpRight, BedDouble, CalendarCheck, ChevronRight, Flame, Footprints, Moon, Utensils } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AccentEdge } from "../Card";
import { Ring, SEVERITY, VerdictChip } from "../CoachNotes";
import { CountUp } from "../CountUp";
import { Vessel } from "../Vessel";
import { Sparkline } from "../Sparkline";
import { energyState, formatKcal, phaseAccent, type HeroId, type NowView } from "../../lib/home";
import { deltaTone, formatDuration, formatMetric } from "../../lib/format";
import { activityStyle, METRIC_STYLES } from "../../lib/metrics";
import { EASE } from "../../lib/motion";
import { time12 } from "../../lib/format";
import { C } from "../../lib/theme";
import type { Brief, HomeEnergy, HomePhase, MetricSummary, Overview, PlannedSessionView } from "../../lib/types";

type Data = Extract<Overview, { has_data: true }>;

const hhmm = time12;
const hm = (h: number) => `${Math.floor(h)}h ${String(Math.round((h % 1) * 60)).padStart(2, "0")}m`;
const metricOf = (ms: MetricSummary[], k: string) => ms.find((m) => m.metric === k) ?? null;

/** The card that leads the Home. It changes with the part of the day the backend named, and slides when that changes while the page is open. */
export function HomeHero({ hero, children }: { hero: HeroId; children: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={hero}
        initial={reduce ? false : { opacity: 0, y: 24, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={reduce ? { opacity: 1 } : { opacity: 0, y: -16, scale: 0.99 }}
        transition={{ duration: reduce ? 0 : 0.55, ease: EASE.outExpo }}
        data-hero={hero}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

function Frame({ accent, label, children, className }: { accent: string; label: string; children: ReactNode; className?: string }) {
  return (
    <section aria-label={label} className={clsx("surface relative overflow-hidden p-5 sm:p-7", className)}>
      <AccentEdge color={accent} strength={0.22} />
      <div className="relative">{children}</div>
    </section>
  );
}

function Stat({ label, value, unit, sub, tone, color, icon: Icon }: { label: string; value: string; unit?: string; sub?: string | null; tone?: "good" | "bad" | "neutral"; color: string; icon: typeof Moon }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow flex items-center gap-1.5 !text-[11px]"><Icon size={12} style={{ color }} aria-hidden /> {label}</p>
      <p className="num mt-1 text-2xl leading-none text-cream">{value}{unit && <span className="ml-1 text-xs font-semibold text-mute">{unit}</span>}</p>
      {sub && <p className={clsx("mt-1 text-[11px] leading-snug", tone === "good" ? "text-lime" : tone === "bad" ? "text-amber" : "text-mute")}>{sub}</p>}
    </div>
  );
}

// ---- wake: sleep, readiness and today's session ----------------------------------------------------------------------------

export function WakeHero({ data, coach, view, phase, hour, onReadiness }: { data: Data; coach: Brief | null; view: NowView | null; phase: HomePhase | null; hour: number; onReadiness?: () => void }) {
  const accent = C[phaseAccent(phase?.phase, hour)];
  const r = coach?.readiness ?? null;
  const sleep = metricOf(data.metrics, "sleep_hours");
  const hrv = metricOf(data.metrics, "hrv");
  const rhr = metricOf(data.metrics, "resting_hr");
  const need = coach?.tonight?.need_h ?? null;
  const sleepStale = sleep ? sleep.latest_day < data.today : false;
  const notSynced = phase?.hints?.sleep === "not_synced" || !sleep || sleepStale;
  const chip = (m: MetricSummary | null) => {
    if (!m || m.delta_pct == null) return { text: m && m.latest_day < data.today ? "earlier day" : "no baseline yet", tone: "neutral" as const };
    const d = m.delta_pct;
    if (Math.abs(d) < 0.5) return { text: "at your usual", tone: "neutral" as const };
    return { text: `${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(Math.abs(d) < 10 ? 1 : 0)}% vs usual`, tone: deltaTone(d, m.higher_is_better) as "good" | "bad" | "neutral" };
  };
  const t = coach?.today;
  return (
    <Frame accent={accent} label="This morning">
      <p className="eyebrow mb-3" style={{ color: accent }}>{view?.eyebrow ?? "Morning"} · how you slept and where you stand</p>
      <div className="flex items-start gap-5 sm:gap-8">
        {r ? (
          <button type="button" onClick={onReadiness} aria-label={`Readiness ${r.score}. Why`} className="shrink-0 text-left">
            <Ring score={r.score} size={128} label={r.live ? "live" : "today"} />
          </button>
        ) : (
          <div className="grid h-32 w-32 shrink-0 place-items-center rounded-full border border-dashed border-line text-center text-[11px] leading-snug text-dim">Readiness<br />after sync</div>
        )}
        <div className="min-w-0 flex-1">
          {coach?.call ? (
            <>
              <h2 className="font-display text-3xl leading-[1.05] text-cream sm:text-4xl">{coach.call.headline}</h2>
              <p className="mt-2 text-sm text-mute">{coach.call.detail}</p>
            </>
          ) : (
            <h2 className="font-display text-3xl leading-[1.05] text-cream sm:text-4xl">{view?.headline ?? "Good morning."}</h2>
          )}
        </div>
      </div>
      <div className="mt-6 grid grid-cols-3 gap-4 border-t border-line pt-5">
        <Stat label="Sleep" icon={Moon} color={C.violet} value={notSynced ? "—" : hm(sleep!.latest)} sub={notSynced ? phase?.copy?.sleep ?? "not synced yet" : need ? `of your ${need.toFixed(need % 1 ? 1 : 0)} h need` : "last night"} tone={notSynced ? "neutral" : need && sleep!.latest >= need ? "good" : "neutral"} />
        <Stat label="HRV" icon={METRIC_STYLES.hrv.icon} color={C.mint} value={hrv ? formatMetric(hrv.latest, "hrv") : "—"} unit={hrv ? "ms" : undefined} sub={hrv ? chip(hrv).text : "not synced"} tone={chip(hrv).tone} />
        <Stat label="Resting HR" icon={METRIC_STYLES.resting_hr.icon} color={C.coral} value={rhr ? formatMetric(rhr.latest, "resting_hr") : "—"} unit={rhr ? "bpm" : undefined} sub={rhr ? chip(rhr).text : "not synced"} tone={chip(rhr).tone} />
      </div>
      {(t || view?.session) && (
        <div className="mt-5 rounded-2xl border border-line bg-ink/40 p-4">
          <p className="eyebrow mb-1"><CalendarCheck size={11} className="mr-1 inline text-gold" aria-hidden />Today</p>
          <p className="font-semibold text-paper">{t?.title ?? view?.session?.title}</p>
          <p className="mt-1 text-sm text-mute">{t?.detail ?? view?.session?.detail}</p>
          <PlanLinks plans={data.planned_today ?? []} />
        </div>
      )}
      {view && view.notes.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm text-dim">{view.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      )}
    </Frame>
  );
}

function PlanLinks({ plans }: { plans: PlannedSessionView[] }) {
  const open = plans.filter((p) => p.status !== "done");
  if (!open.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {open.map((p) => (
        <Link key={p.id} to={p.gym ? `/workout/${p.id}` : "/plan"} className="chip text-paper hover:text-cream pointer-coarse:py-2">
          {p.gym ? "Open the workout" : "See the plan"} <ChevronRight size={11} />
        </Link>
      ))}
    </div>
  );
}

// ---- session: what you just did ---------------------------------------------------------------------------------------------

export function SessionHero({ coach, energy, view, phase, hour }: { coach: Brief | null; energy: HomeEnergy | null | undefined; view: NowView | null; phase: HomePhase | null; hour: number }) {
  const accent = C[phaseAccent(phase?.phase, hour)];
  const today = coach?.recent.label === "Today" ? coach.recent.items : [];
  const s = today[0] ?? null;
  const t = coach?.today;
  const kcal = energy?.workout_active_kcal ?? null;
  if (!s) {
    return (
      <Frame accent={accent} label="After your session">
        <p className="eyebrow mb-2" style={{ color: accent }}>{view?.eyebrow ?? "After your session"}</p>
        <h2 className="font-display text-3xl leading-[1.05] text-cream sm:text-4xl">{t?.kind === "done" ? t.title : view?.headline ?? "Session done."}</h2>
        <p className="mt-2 text-mute">{t?.kind === "done" ? t.detail : view?.session?.detail ?? "The analysis appears once the activity has synced."}</p>
        {energy?.copy?.refuel && <p className="mt-3 text-sm text-paper">{energy.copy.refuel}</p>}
      </Frame>
    );
  }
  const style = activityStyle(s.type, s.family);
  const Icon = style.icon;
  const sev = s.note ? SEVERITY[s.note.severity] : null;
  const stats = [
    s.moving_s ? { k: "time", v: formatDuration(s.moving_s) } : null,
    s.distance_m ? { k: "km", v: (s.distance_m / 1000).toFixed(1) } : null,
    s.avg_hr ? { k: "bpm", v: Math.round(s.avg_hr).toString() } : null,
    { k: "load", v: s.load.toString() },
  ].filter((x): x is { k: string; v: string } => x !== null);
  return (
    <Frame accent={style.color} label="After your session" className="afterglow">
      <div className="flex items-start gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl" style={{ background: `${style.color}1f`, color: style.color }}><Icon size={22} strokeWidth={1.75} /></div>
        <div className="min-w-0 flex-1">
          <p className="eyebrow mb-1" style={{ color: style.color }}>{view?.eyebrow ?? "After your session"} · {style.label}</p>
          <h2 className="font-display text-3xl leading-[1.05] text-cream sm:text-4xl">{s.name}</h2>
        </div>
        {s.verdict && <VerdictChip v={s.verdict} />}
      </div>
      <dl className="mt-5 flex flex-wrap gap-x-7 gap-y-3">
        {stats.map((x) => (
          <div key={x.k}>
            <dd className="num text-3xl leading-none text-cream">{x.v}</dd>
            <dt className="mt-1 text-[11px] tracking-widest text-dim uppercase">{x.k}</dt>
          </div>
        ))}
        {kcal != null && kcal > 0 && (
          <div>
            <dd className="num text-3xl leading-none text-gold">+{formatKcal(kcal)}</dd>
            <dt className="mt-1 text-[11px] tracking-widest text-dim uppercase">kcal · estimate</dt>
          </div>
        )}
      </dl>
      {s.intensity && (
        <div className="mt-4 flex h-2 overflow-hidden rounded-full" role="img" aria-label={`Easy ${s.intensity.easy_pct}%, moderate ${s.intensity.moderate_pct}%, hard ${s.intensity.hard_pct}%`}>
          <span style={{ width: `${s.intensity.easy_pct}%`, background: C.mint }} />
          <span style={{ width: `${s.intensity.moderate_pct}%`, background: C.lime }} />
          <span style={{ width: `${s.intensity.hard_pct}%`, background: C.coral }} />
        </div>
      )}
      {s.note && sev && (
        <p className="mt-4 text-sm"><span className="font-semibold" style={{ color: sev.color }}>{s.note.title}.</span> <span className="text-mute">{s.note.detail}</span></p>
      )}
      <p className="mt-4 text-sm text-paper">{view?.headline}</p>
      {energy?.copy?.refuel && <p className="mt-1 text-sm text-mute">{energy.copy.refuel}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link to={`/activities/${s.id}`} className="pop pop-ghost min-h-[44px] !text-[12px]">Open analysis <ArrowUpRight size={13} /></Link>
        <Link to="/food" className="pop pop-ghost min-h-[44px] !text-[12px]"><Utensils size={13} aria-hidden /> Log the refuel</Link>
      </div>
    </Frame>
  );
}

// ---- wind-down: bed time, the day's totals, tomorrow ------------------------------------------------------------------------

export function WinddownHero({ data, coach, energy, view, phase, hour }: { data: Data; coach: Brief | null; energy: HomeEnergy | null | undefined; view: NowView | null; phase: HomePhase | null; hour: number }) {
  const accent = C[phaseAccent(phase?.phase, hour)];
  const t = coach?.tonight ?? null;
  const steps = metricOf(data.metrics, "steps");
  const stepsToday = steps && steps.latest_day === data.today ? steps.latest : null;
  const e = energyState(energy, phase?.hints?.calories, data.source_id === "demo");
  const burned = e.kind === "ok" ? energy!.burned!.total! : null;
  const eaten = e.kind === "ok" && e.hasLog ? energy!.eaten!.kcal : null;
  const nowMin = hour * 60;
  const bedSoon = t ? (((t.bed_min - nowMin) % 1440) + 1440) % 1440 : null;
  return (
    <Frame accent={accent} label="Winding down">
      <p className="eyebrow mb-2" style={{ color: accent }}>{view?.eyebrow ?? "Winding down"}</p>
      {t ? (
        <Link to="/coach#sleep" className="group block">
          <p className="text-sm text-mute">In bed by</p>
          <p className="leading-none"><Vessel fill={Math.max(0, Math.min(1, (nowMin - 6 * 60) / Math.max(60, t.bed_min - 6 * 60)))} color={accent} className="text-[clamp(64px,23vw,120px)]">{hhmm(t.bed_min)}</Vessel></p>
          <p className="mt-1 text-sm text-mute">
            {t.tonight_h.toFixed(1)} h to wake at <span className="num text-paper">{hhmm(t.wake_min)}</span>
            {bedSoon != null && bedSoon > 0 && bedSoon <= 180 ? ` · in about ${bedSoon >= 60 ? `${Math.floor(bedSoon / 60)} h ${bedSoon % 60 ? `${bedSoon % 60} min` : ""}` : `${bedSoon} min`}` : ""}
          </p>
          {t.capped ? <p className="mt-1 text-xs text-dim">An hour earlier than usual; keep stepping toward {t.ideal_h.toFixed(1)} h over the week.</p>
            : (t.extra_load_min > 0 || t.repay_min > 0) && <p className="mt-1 text-xs text-dim">Your {t.need_h} h need{t.extra_load_min ? ` +${t.extra_load_min} min for today's training` : ""}{t.repay_min ? ` +${t.repay_min} min toward ${t.debt_h} h of debt` : ""}.</p>}
        </Link>
      ) : (
        <h2 className="font-display text-3xl leading-[1.05] text-cream sm:text-4xl">{view?.headline ?? "The day is done."}</h2>
      )}
      <div className="mt-6 grid grid-cols-3 gap-4 border-t border-line pt-5">
        <Stat label="Steps" icon={Footprints} color={C.lime} value={stepsToday != null ? Math.round(stepsToday).toLocaleString() : "—"} sub={stepsToday != null ? "today" : "not synced today"} />
        <Stat label="Burned" icon={Flame} color={C.gold} value={burned != null ? formatKcal(burned) : "—"} unit={burned != null ? "kcal" : undefined} sub={burned != null ? "so far, estimate" : e.kind === "just_started" ? "day just started" : "not reported"} />
        <Stat label="Eaten" icon={Utensils} color={C.sky} value={eaten != null ? formatKcal(eaten) : "—"} unit={eaten != null ? "kcal" : undefined} sub={eaten != null ? "logged" : "nothing logged"} />
      </div>
      {(view?.session || (coach?.today.kind === "done" && coach.today.next)) && (
        <div className="mt-5 rounded-2xl border border-line bg-ink/40 p-4">
          <p className="eyebrow mb-1"><BedDouble size={11} className="mr-1 inline text-violet" aria-hidden />{coach?.today.kind === "done" && coach.today.next ? "Tomorrow" : view?.session?.title}</p>
          <p className="text-sm text-paper">{coach?.today.kind === "done" && coach.today.next ? coach.today.next : view?.session?.detail}</p>
        </div>
      )}
      {view && view.notes.length > 0 && <ul className="mt-4 space-y-1 text-sm text-dim">{view.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </Frame>
  );
}

// ---- the compact calories strip, for the hours when calories do not lead ------------------------------------------------------

export function CalorieStrip({ energy, phase, isDemo, full }: { energy: HomeEnergy | null | undefined; phase: HomePhase | null; isDemo: boolean; full: ReactNode }) {
  const [open, setOpen] = useState(false);
  const state = energyState(energy, phase?.hints?.calories, isDemo);
  if (open) return <>{full}<button type="button" onClick={() => setOpen(false)} className="eyebrow mt-2 w-full py-2 text-center hover:text-paper">Show less</button></>;
  if (state.kind !== "ok") {
    return (
      <Link to="/food" className="surface surface-hover press flex items-center gap-4 p-4" aria-label="Calories and food log">
        <Flame size={18} className="shrink-0 text-gold" aria-hidden />
        <span className="min-w-0 flex-1 text-sm text-mute">{state.kind === "just_started" ? "Burn and food totals start from here." : state.kind === "unsupported" ? (state.demo ? "Demo data has no calorie burn." : energy?.copy?.status ?? "No calorie burn reported yet.") : "Calories appear once Garmin and your food log are available."}</span>
        <ChevronRight size={16} className="shrink-0 text-dim" />
      </Link>
    );
  }
  const e = energy!;
  const burned = e.burned!.total!;
  const eaten = state.hasLog ? (e.eaten!.kcal as number) : null;
  const target = e.target ? e.target.kcal + (e.eat_back_kcal ?? 0) : null;
  const scale = Math.max(burned, eaten ?? 0, target ?? 0, 1);
  const left = e.left ?? null;
  const above = e.above_by ?? null;
  const tail = state.showLeft && left != null ? `${formatKcal(left)} left` : state.showLeft && above != null ? `${formatKcal(above)} above` : target ? `target ${formatKcal(target)}` : "no target";
  const spark = (e.spark ?? []).filter((d) => d.total != null && !d.partial).map((d) => d.total as number).slice(-10);
  return (
    <button type="button" onClick={() => setOpen(true)} className="surface surface-hover press block w-full p-4 text-left" aria-expanded={open} aria-label={`Calories: ${formatKcal(burned)} burned, ${eaten != null ? `${formatKcal(eaten)} eaten` : "nothing logged"}, ${tail}. Show details`}>
      <div className="flex items-center gap-4">
        <Flame size={18} className="shrink-0 text-gold" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-x-3 text-sm">
            <span className="num text-xl text-cream"><CountUp value={burned} format={formatKcal} immediate /></span><span className="text-mute">burned</span>
            <span className="num text-xl text-cream">{eaten != null ? formatKcal(eaten) : "—"}</span><span className="text-mute">{eaten != null ? "eaten" : "nothing logged"}</span>
            <span className={clsx("ml-auto num", above != null ? "text-amber" : "text-sky")}>{tail}</span>
          </p>
          <div className="mt-2 flex h-1.5 gap-1 overflow-hidden">
            <span className="rounded-full" style={{ width: `${(burned / scale) * 100}%`, background: C.gold }} />
          </div>
          <div className="mt-1 flex h-1.5 gap-1 overflow-hidden">
            {eaten != null && <span className="rounded-full" style={{ width: `${(eaten / scale) * 100}%`, background: C.sky }} />}
          </div>
        </div>
        {spark.length >= 3 && <Sparkline values={spark} color={C.gold} height={26} className="hidden w-16 shrink-0 sm:block" />}
        <ChevronRight size={16} className="shrink-0 text-dim" />
      </div>
    </button>
  );
}
