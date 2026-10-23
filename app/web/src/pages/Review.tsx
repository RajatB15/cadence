import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ChevronLeft, ChevronRight, Flame, Target } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { PATTERN_LABEL } from "../components/StrengthClass";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { Review } from "../lib/types";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const at = (s: string) => new Date(`${s}T12:00:00`);
const monthName = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" });
const clock = (m: number) => {
  const v = ((Math.round(m) % 1440) + 1440) % 1440;
  return `${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`;
};
const pace = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

function shift(r: Review, by: number): string {
  const d = at(r.start);
  if (r.kind === "week") d.setDate(d.getDate() + 7 * by);
  else d.setMonth(d.getMonth() + by, 1);
  return iso(d);
}

export function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") === "month" ? "month" : "week";
  const start = params.get("start") ?? undefined;
  const q = useQuery({ queryKey: ["review", kind, start], queryFn: () => api.review(kind, start) });
  const go = (k: "week" | "month", s?: string) => setParams(s ? { kind: k, start: s } : { kind: k });
  return (
    <>
      <PageHeader eyebrow="Reviews" title={<>Look <em className="text-gold">back.</em></>}>
        <Segmented label="Period" options={[{ value: "week", label: "Week" }, { value: "month", label: "Month" }]} value={kind} onChange={(k) => go(k)} />
      </PageHeader>
      {q.isPending ? <LoadingBlock height={520} /> : q.isError ? <ErrorBlock error={q.error} retry={() => q.refetch()} /> : !q.data.has_data ? (
        <div className="surface p-12 text-center text-mute">Sync some training to see reviews.</div>
      ) : <Body r={q.data} go={go} />}
    </>
  );
}

function Body({ r, go }: { r: Review; go: (k: "week" | "month", s?: string) => void }) {
  const prev = shift(r, -1);
  const next = shift(r, 1);
  const title = r.kind === "month" ? monthName.format(at(r.start)) : `${formatDate(r.start)} – ${formatDate(r.end)}`;
  const t = r.training;
  const v = r.vs_previous;
  return (
    <div className="space-y-6">
      <section className="flex items-center justify-between gap-3">
        <button type="button" aria-label="Previous" disabled={prev < r.first} onClick={() => go(r.kind, prev)}
          className="grid h-10 w-10 place-items-center border border-line-strong text-mute hover:text-paper disabled:opacity-30"><ChevronLeft size={18} /></button>
        <div className="text-center">
          <p className="eyebrow">{title}{!r.complete && " · so far"}</p>
          <h2 className="mt-1 font-display text-3xl text-cream sm:text-5xl">{r.verdict}</h2>
        </div>
        <button type="button" aria-label="Next" disabled={next > r.today} onClick={() => go(r.kind, next)}
          className="grid h-10 w-10 place-items-center border border-line-strong text-mute hover:text-paper disabled:opacity-30"><ChevronRight size={18} /></button>
      </section>

      <section className="surface flex items-start gap-4 p-5 sm:p-6" style={{ borderLeft: "3px solid #c8f560" }}>
        <Target size={20} className="mt-0.5 shrink-0 text-lime" />
        <div>
          <p className="eyebrow mb-1">Focus {r.kind === "week" ? "for next week" : "for next month"}</p>
          <p className="font-semibold text-paper">{r.focus.title}</p>
          <p className="mt-1 text-sm text-mute">{r.focus.detail}</p>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label="Sessions" value={t.sessions} delta={v.sessions} />
        <Kpi label="Hours" value={t.hours.toFixed(1)} delta={v.hours} />
        <Kpi label="Load" value={t.load} delta={v.load} />
        <Kpi label="Fitness" value={r.fitness.end?.toFixed(0) ?? "—"} delta={r.fitness.start != null && r.fitness.end != null ? +(r.fitness.end - r.fitness.start).toFixed(1) : null} hint="change this period" />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Training">
          <Row k="By sport" v={Object.entries(t.by_sport).map(([s, n]) => `${s} ${n}`).join(" · ") || "—"} />
          {t.run_km > 0 && <Row k="Running" v={`${t.run_km} km${v.run_km != null ? ` (${v.run_km >= 0 ? "+" : ""}${v.run_km} km)` : ""}`} />}
          {t.ride_km > 0 && <Row k="Riding" v={`${t.ride_km} km`} />}
          <Row k="Quality sessions" v={t.quality} />
          {t.long_run_min > 0 && <Row k="Longest run" v={`${t.long_run_min} min`} />}
          {t.easy_pct != null && <Row k="Easy time" v={`${t.easy_pct}%${t.hard_sessions_pct != null ? ` · ${t.hard_sessions_pct}% of sessions hard` : ""}`} />}
          <Row k="Rest days" v={t.rest_days} />
          {t.strain != null && <Row k="All-day strain" v={`${t.strain} (${t.everyday_strain} everyday)`} />}
          {r.hot_sessions > 0 && <Row k="Hot sessions" v={r.hot_sessions} />}
        </Card>
        <Card title="Plan">
          {r.plan.planned ? (
            <>
              <Row k="Planned" v={`${r.plan.done} of ${r.plan.planned} done${r.plan.missed ? ` · ${r.plan.missed} missed` : ""}`} />
              {r.plan.predicted_load != null && <Row k="Load, done sessions" v={`${r.plan.actual_load} actual vs ${r.plan.predicted_load} predicted`} />}
            </>
          ) : (
            <p className="text-sm text-mute">Nothing planned. <Link to="/plan" className="text-gold hover:underline">Plan next week</Link> to see adherence here.</p>
          )}
          {r.fitness.form != null && <Row k="Form at the end" v={`${r.fitness.form > 0 ? "+" : ""}${r.fitness.form.toFixed(0)}${r.fitness.acwr ? ` · acute:chronic ${r.fitness.acwr.toFixed(2)}` : ""}`} />}
        </Card>
        <Card title="Recovery">
          <Row k="Readiness" v={r.recovery.readiness != null ? `${r.recovery.readiness}${v.readiness != null ? ` (${v.readiness >= 0 ? "+" : ""}${v.readiness})` : ""}` : "—"} />
          {r.recovery.hrv != null && <Row k="HRV" v={`${r.recovery.hrv} ms${r.recovery.hrv_base ? ` vs ${r.recovery.hrv_base} before` : ""}`} />}
          {r.recovery.rhr != null && <Row k="Resting HR" v={`${r.recovery.rhr} bpm${r.recovery.rhr_base ? ` vs ${r.recovery.rhr_base} before` : ""}`} />}
          <Row k="Warning days" v={r.recovery.warning_days} tone={r.recovery.warning_days ? "text-amber" : undefined} />
        </Card>
        <Card title="Sleep">
          <Row k="Average" v={r.sleep.avg_hours != null ? `${r.sleep.avg_hours} h vs ${r.sleep.need} h need${v.sleep != null ? ` (${v.sleep >= 0 ? "+" : ""}${v.sleep} h)` : ""}` : "—"} />
          <Row k="Nights at need" v={`${r.sleep.nights_at_need} of ${r.sleep.nights}`} />
          {r.sleep.avg_bedtime_min != null && <Row k="Average lights out" v={clock(r.sleep.avg_bedtime_min)} />}
          {r.sleep.regularity != null && <Row k="Regularity (SRI)" v={r.sleep.regularity} />}
        </Card>
        {r.habits.logged_days > 0 && (
          <Card title="Habits">
            <Row k="Days logged" v={`${r.habits.logged_days} of ${r.days}`} />
            {r.habits.items.slice(0, 6).map((h) => (
              <Row key={h.key} k={h.label} v={h.total != null ? `${h.total} ${h.unit} over ${h.days} days` : `${h.days} days`} />
            ))}
          </Card>
        )}
        {r.strength.sessions > 0 && (
          <Card title="Strength">
            <Row k="Sessions" v={`${r.strength.sessions}${r.strength.heavy_lower ? ` · ${r.strength.heavy_lower} heavy lower` : ""}`} />
            {Object.keys(r.strength.patterns).length > 0 && <Row k="Patterns" v={Object.keys(r.strength.patterns).map((p) => PATTERN_LABEL[p] ?? p).join(", ")} />}
          </Card>
        )}
        {r.trends && (
          <Card title="Month trends">
            {r.trends.critical_speed_pace[1] != null && <Row k="Critical speed" v={`${pace(r.trends.critical_speed_pace[1]!)}/km${r.trends.critical_speed_pace[0] ? ` (was ${pace(r.trends.critical_speed_pace[0])})` : ""}`} />}
            {r.trends.efficiency_pct != null && <Row k="Run efficiency" v={`${r.trends.efficiency_pct > 0 ? "+" : ""}${r.trends.efficiency_pct}% vs the month before`} />}
            {r.trends.vo2max[1] != null && <Row k="VO₂ max" v={`${r.trends.vo2max[1]}${r.trends.vo2max[0] != null ? ` (was ${r.trends.vo2max[0]})` : ""}`} />}
            {r.trends.weight[1] != null && <Row k="Weight" v={`${r.trends.weight[1]} kg${r.trends.weight[0] != null ? ` (was ${r.trends.weight[0]})` : ""}`} />}
          </Card>
        )}
        {r.highlights.length > 0 && (
          <Card title="Highlights">
            {r.highlights.map((h, i) => (
              <Link key={`${h.id}-${i}`} to={`/activities/${h.id}`} className="flex items-baseline justify-between gap-3 border-b border-line py-2 text-sm hover:text-paper">
                <span className="flex min-w-0 items-center gap-2 text-paper"><Flame size={13} className="shrink-0 text-gold" /><span className="truncate">{["Biggest", "Longest", "Fastest"][i] ?? ""}: {h.name}</span></span>
                <span className="num shrink-0 text-xs text-mute">{h.value}</span>
              </Link>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, value, delta, hint }: { label: string; value: ReactNode; delta: number | null; hint?: string }) {
  return (
    <div className="surface p-4">
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-3xl text-cream">{value}</p>
      <p className={clsx("num text-xs", delta == null ? "text-dim" : delta >= 0 ? "text-lime" : "text-amber")}>
        {delta == null ? hint ?? "" : `${delta >= 0 ? "+" : ""}${delta} ${hint ? "" : "vs before"}`}
      </p>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="surface p-5 sm:p-6">
      <h3 className="mb-3 font-display text-2xl text-cream">{title}</h3>
      <div className="space-y-0.5">{children}</div>
    </section>
  );
}

function Row({ k, v, tone }: { k: string; v: ReactNode; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line/60 py-2 text-sm">
      <span className="text-mute">{k}</span>
      <span className={clsx("num text-right", tone ?? "text-paper")}>{v}</span>
    </div>
  );
}
