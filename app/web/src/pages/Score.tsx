import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowDownRight, ArrowUpRight, Info } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { Ring, readyColor } from "../components/CoachNotes";
import { CountUp } from "../components/CountUp";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { ScoreFactor, ScoreReport } from "../lib/types";

type Report = Extract<ScoreReport, { has_data: true }>;

const GROUP_COLOR: Record<string, string> = { train: "#c8f560", recover: "#9b8cff", sleep: "#6cc7ff", move: "#ffbe55" };

export function ScorePage() {
  const [days, setDays] = useState(90);
  const query = useQuery({ queryKey: ["score", days], queryFn: () => api.score(days) });
  if (query.isPending) return <LoadingBlock height={640} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  if (!query.data.has_data) {
    return <div className="surface p-12 text-center text-mute">Sync Garmin data to compute your Cadence score.</div>;
  }
  const r = query.data;
  return (
    <>
      <PageHeader
        eyebrow={<>Cadence score · {formatDate(r.day)}</>}
        title={
          <>
            One number, <em className="text-gold">every lever.</em>
          </>
        }
      />
      <div className="space-y-6">
        <Hero r={r} />
        <PointsBar r={r} />
        <Gaps gaps={r.gaps} />
        <History r={r} days={days} setDays={setDays} />
        {r.groups.map((g) => (
          <GroupSection key={g.key} r={r} groupKey={g.key} />
        ))}
        <Methods />
      </div>
    </>
  );
}

// ---- hero: overall ring, group rings, radar --------------------------------------

function Hero({ r }: { r: Report }) {
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "item" },
      radar: {
        indicator: r.factors.map((f) => ({ name: f.label, max: 100 })),
        radius: "68%",
        splitNumber: 4,
        axisName: { color: "#8d8a82", fontSize: 10 },
        splitLine: { lineStyle: { color: "#262629" } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: "#262629" } },
      },
      series: [
        {
          type: "radar",
          symbol: "circle",
          symbolSize: 4,
          data: [{ value: r.factors.map((f) => f.score), name: "Score" }],
          lineStyle: { color: readyColor(r.score), width: 2 },
          itemStyle: { color: readyColor(r.score) },
          areaStyle: { color: `${readyColor(r.score)}33` },
        },
      ],
    }),
    [r],
  );
  return (
    <section className="relative overflow-hidden border-y border-line py-10">
      <div className="pointer-events-none absolute -top-24 left-0 h-80 w-80 rounded-full opacity-15 blur-3xl" style={{ background: readyColor(r.score) }} />
      <div className="grid items-center gap-10 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,24rem)]">
        <div className="mx-auto text-center">
          <Ring score={r.score} size={210} label="cadence" />
          <p className="mt-3 font-display text-3xl text-cream">{r.label}</p>
          {r.delta_7d != null && (
            <p className={clsx("num mt-1 inline-flex items-center gap-1 text-sm", r.delta_7d >= 0 ? "text-lime" : "text-coral")}>
              {r.delta_7d >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              {Math.abs(r.delta_7d)} vs last week
            </p>
          )}
        </div>
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
          {r.groups.map((g) => (
            <a key={g.key} href={`#${g.key}`} className="group text-center">
              <div className="mx-auto w-fit transition-transform group-hover:scale-105">
                <GroupRing score={g.score} color={GROUP_COLOR[g.key]} />
              </div>
              <p className="mt-2 font-semibold text-paper">{g.label}</p>
              <p className="text-[11px] leading-snug text-dim">{Math.round(g.weight * 100)}% of score</p>
            </a>
          ))}
        </div>
        <Chart option={option} height={300} label="Score shape across every factor" />
      </div>
    </section>
  );
}

function GroupRing({ score, color }: { score: number; color: string }) {
  const r = 34;
  const circ = 2 * Math.PI * r;
  return (
    <div className="relative h-24 w-24">
      <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#1c1c1f" strokeWidth="6" />
        <motion.circle
          cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          whileInView={{ strokeDashoffset: circ * (1 - score / 100) }}
          viewport={{ once: true }}
          transition={{ duration: 1.1, ease: [0.2, 0.9, 0.1, 1] }}
        />
      </svg>
      <span className="num absolute inset-0 grid place-items-center text-2xl text-paper">
        <CountUp value={score} format={(v) => Math.round(v).toString()} duration={1.1} />
      </span>
    </div>
  );
}

// ---- where the 100 points go ---------------------------------------------------------

function PointsBar({ r }: { r: Report }) {
  const lost = r.factors.filter((f) => f.points_lost > 0).sort((a, b) => b.points_lost - a.points_lost);
  return (
    <section className="surface p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-2">Where the 100 points go</p>
          <h2 className="font-display text-3xl text-cream">
            {r.score} earned · <span className="text-amber">{100 - r.score} on the table</span>
          </h2>
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-mute">
          {r.groups.map((g) => (
            <span key={g.key} className="flex items-center gap-2">
              <span className="h-2 w-2" style={{ background: GROUP_COLOR[g.key] }} /> {g.label}
            </span>
          ))}
        </div>
      </div>
      <div className="flex h-8 overflow-hidden">
        <motion.div
          className="grid place-items-center text-xs font-semibold text-ink"
          style={{ background: readyColor(r.score) }}
          initial={{ width: 0 }}
          whileInView={{ width: `${r.score}%` }}
          viewport={{ once: true }}
          transition={{ duration: 1 }}
        >
          {r.score}
        </motion.div>
        {lost.map((f) => (
          <motion.div
            key={f.key}
            title={`${f.label}: −${f.points_lost} (${f.value} → ${f.target})`}
            className="border-l border-ink"
            style={{ background: `${GROUP_COLOR[f.group]}${f.points_lost >= 2 ? "cc" : "66"}` }}
            initial={{ width: 0 }}
            whileInView={{ width: `${f.points_lost}%` }}
            viewport={{ once: true }}
            transition={{ duration: 1, delay: 0.3 }}
          />
        ))}
      </div>
      <p className="mt-3 text-xs text-dim">Coloured slices are points lost, by area. Hover a slice for the factor behind it.</p>
    </section>
  );
}

function Gaps({ gaps }: { gaps: ScoreFactor[] }) {
  if (!gaps.length) return null;
  const max = Math.max(...gaps.map((g) => g.points_lost));
  return (
    <section className="surface p-6 sm:p-8">
      <p className="eyebrow mb-2">What's holding the score back</p>
      <h2 className="mb-6 font-display text-3xl text-cream">Close these gaps first</h2>
      <ol className="space-y-5">
        {gaps.slice(0, 6).map((g, i) => (
          <li key={g.key} className="grid gap-x-6 gap-y-2 sm:grid-cols-[2rem_minmax(0,14rem)_minmax(0,1fr)]">
            <span className="num text-2xl text-dim">{i + 1}</span>
            <div>
              <p className="font-semibold text-paper">{g.label}</p>
              <p className="text-xs text-mute">
                <span className="num text-paper">{g.value}</span> → {g.target}
              </p>
            </div>
            <div>
              <div className="flex items-center gap-3">
                <div className="h-2 flex-1 bg-slate">
                  <motion.div
                    className="h-full"
                    style={{ background: GROUP_COLOR[g.group] }}
                    initial={{ width: 0 }}
                    whileInView={{ width: `${(g.points_lost / max) * 100}%` }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.9, delay: i * 0.05 }}
                  />
                </div>
                <span className="num w-14 shrink-0 text-right text-amber">−{g.points_lost.toFixed(1)}</span>
              </div>
              <p className="mt-2 text-sm text-mute">
                <span className="text-gold">→ </span>
                {g.tip}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ---- history -------------------------------------------------------------------------

function History({ r, days, setDays }: { r: Report; days: number; setDays: (d: number) => void }) {
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis" },
      legend: undefined,
      yAxis: { ...chartBase.yAxis, min: 0, max: 100, scale: false },
      series: [
        {
          name: "Cadence", type: "line", data: r.history.map((h) => [h.day, h.score]), symbol: "none", smooth: 0.3,
          lineStyle: { color: "#f2e8cf", width: 3 },
          areaStyle: { color: "rgba(242,232,207,0.06)" },
          markArea: {
            silent: true,
            data: [
              [{ yAxis: 85, itemStyle: { color: "rgba(200,245,96,0.06)" } }, { yAxis: 100 }],
              [{ yAxis: 0, itemStyle: { color: "rgba(255,106,85,0.05)" } }, { yAxis: 55 }],
            ],
          },
        },
        ...r.groups.map((g) => ({
          name: g.label, type: "line", data: r.history.map((h) => [h.day, h[g.key] ?? null]), symbol: "none", smooth: 0.3,
          lineStyle: { color: GROUP_COLOR[g.key], width: 1.4, opacity: 0.8 },
        })),
      ],
    }),
    [r],
  );
  return (
    <section className="surface p-6 sm:p-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-2">Trend</p>
          <h2 className="font-display text-3xl text-cream">How your score has moved</h2>
        </div>
        <Segmented label="Range" options={[{ value: 30, label: "30D" }, { value: 90, label: "90D" }, { value: 365, label: "1Y" }]} value={days} onChange={setDays} />
      </div>
      <Chart option={option} height={320} label="Cadence score history" />
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-mute">
        <span className="flex items-center gap-2"><span className="h-0.5 w-4 bg-cream" /> Cadence</span>
        {r.groups.map((g) => (
          <span key={g.key} className="flex items-center gap-2">
            <span className="h-0.5 w-4" style={{ background: GROUP_COLOR[g.key] }} /> {g.label}
          </span>
        ))}
      </div>
    </section>
  );
}

// ---- per-group factor cards -------------------------------------------------------------

function GroupSection({ r, groupKey }: { r: Report; groupKey: string }) {
  const g = r.groups.find((x) => x.key === groupKey)!;
  const factors = r.factors.filter((f) => f.group === groupKey);
  const color = GROUP_COLOR[groupKey];
  return (
    <section id={groupKey} className="surface scroll-mt-8 p-6 sm:p-8" style={{ borderTop: `2px solid ${color}` }}>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-2">{g.blurb}</p>
          <h2 className="font-display text-3xl text-cream">
            {g.label} <span className="num" style={{ color }}>{g.score}</span>
          </h2>
        </div>
        <p className="text-xs text-dim">{Math.round(g.weight * 100)}% of your Cadence score</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {factors.map((f, i) => (
          <motion.article
            key={f.key}
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.04 }}
            className="flex flex-col border border-line bg-ink/40 p-5"
          >
            <div className="flex items-baseline justify-between gap-3">
              <p className="font-semibold text-paper">{f.label}</p>
              <p className="num text-3xl" style={{ color: readyColor(f.score) }}>
                <CountUp value={f.score} format={(v) => Math.round(v).toString()} />
              </p>
            </div>
            <div className="mt-2 h-1.5 bg-slate">
              <motion.div
                className="h-full"
                style={{ background: readyColor(f.score) }}
                initial={{ width: 0 }}
                whileInView={{ width: `${f.score}%` }}
                viewport={{ once: true }}
                transition={{ duration: 0.9 }}
              />
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-[10px] tracking-widest text-dim uppercase">You</dt>
                <dd className="num text-paper">{f.value}</dd>
              </div>
              <div>
                <dt className="text-[10px] tracking-widest text-dim uppercase">Target</dt>
                <dd className="text-paper">{f.target}</dd>
              </div>
            </dl>
            <p className="mt-4 text-xs leading-relaxed text-mute">{f.tip}</p>
            {f.points_lost >= 0.5 && <p className="num mt-auto pt-3 text-xs text-amber">−{f.points_lost.toFixed(1)} points</p>}
          </motion.article>
        ))}
      </div>
    </section>
  );
}

function Methods() {
  return (
    <details className="surface group p-6 text-sm text-mute">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-paper">
        <Info size={16} className="text-gold" /> How the Cadence score works
      </summary>
      <div className="mt-4 max-w-3xl space-y-2 leading-relaxed">
        <p>
          Four areas, each a weighted average of its factors: <b className="text-paper">Train 30%</b> (load balance, intensity
          balance, hard-day spacing, consistency, fitness trend, aerobic efficiency), <b className="text-paper">Recover 30%</b> (HRV
          against your Garmin balanced range, resting HR vs your 60-day normal, Body Battery, daytime stress),{" "}
          <b className="text-paper">Sleep 25%</b> (duration vs 8 h, Garmin sleep score, bedtime regularity) and{" "}
          <b className="text-paper">Move 15%</b> (steps vs 10,000, intensity minutes vs WHO's 150 a week).
        </p>
        <p>
          Most factors use the last 7 days; training structure uses 4 weeks and consistency 12. Every factor is recomputed for each
          past day, so the trend is honest. A factor with no data is left out rather than counted as zero. &quot;Points lost&quot; is how much
          the overall score would rise if that factor reached 100.
        </p>
      </div>
    </details>
  );
}
