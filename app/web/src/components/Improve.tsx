import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { BookOpen, ChevronDown, Compass, Eye } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import {
  ASSOCIATION_NOTE,
  SECTION_LABEL,
  ciExcludesZero,
  ciText,
  citationLabel,
  confidenceLabel,
  doiUrl,
  driverSentence,
  homeCard,
  neededText,
  numberText,
  blockedText,
  reviewNote,
  watchLabel,
  normalizeCitations,
  orderDrivers,
  orderStarts,
  orderWatch,
  progressPct,
  sampleText,
  sectionStatuses,
  signed,
  verdictText,
  type SectionKey,
} from "../lib/improve";
import type { ImproveBenchmark, ImproveCitation, ImproveDriver, ImproveNumber, ImproveReport, ImproveStart, ImproveWatch } from "../lib/types";
import { Sheet } from "./Sheet";
import { ErrorBlock } from "./Shell";

type Cites = Record<string, ImproveCitation>;

function CitationChips({ ids, cites, onOpen }: { ids?: string[]; cites: Cites; onOpen: (id: string) => void }) {
  if (!ids?.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onOpen(id)}
          aria-label={`Source: ${citationLabel(id, cites)}`}
          className="chip min-h-11 items-center normal-case tracking-normal hover:text-paper"
        >
          <BookOpen size={12} className="text-gold" aria-hidden /> {citationLabel(id, cites)}
        </button>
      ))}
    </div>
  );
}

function Numbers({ numbers }: { numbers?: Record<string, ImproveNumber> }) {
  const entries = Object.entries(numbers ?? {}).filter(([, v]) => v != null);
  if (!entries.length) return null;
  return (
    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt className="text-[11px] text-dim">{k.replace(/_/g, " ")}</dt>
          <dd className="num text-lg text-paper">{numberText(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function CiBar({ ci, diff, unit }: { ci?: [number, number] | null; diff?: number | null; unit?: string }) {
  if (!ci || ci.length !== 2 || diff == null) return null;
  const lo = Math.min(ci[0], 0), hi = Math.max(ci[1], 0);
  const span = hi - lo || 1;
  const pos = (v: number) => `${((v - lo) / span) * 100}%`;
  const text = `Estimate ${signed(diff)} ${unit ?? ""}, ${ciText(ci, unit) ?? ""}${ciExcludesZero(ci) === false ? ", range includes no difference" : ""}`;
  return (
    <div className="mt-3" role="img" aria-label={text}>
      <div className="relative h-5">
        <div className="absolute inset-x-0 top-2 h-1 bg-line-strong" />
        <div className="absolute top-1 h-3 bg-mute/50" style={{ left: pos(ci[0]), width: `${((ci[1] - ci[0]) / span) * 100}%` }} />
        <div className="absolute top-0 h-5 w-px bg-paper" style={{ left: pos(0) }} title="no difference" />
        <div className="absolute top-0.5 h-4 w-1.5 bg-gold" style={{ left: pos(diff) }} />
      </div>
      <p className="mt-1 text-[11px] text-dim">Line is no difference · bar is the 95% range · gold is the estimate</p>
    </div>
  );
}

function Collecting({ label, text }: { label: string; text: string }) {
  return (
    <div className="border border-dashed border-line-strong p-4 text-sm text-mute">
      <p className="text-paper">{label}: not enough data yet</p>
      <p className="mt-1">{text}</p>
    </div>
  );
}

function DriverCard({ d, outcome }: { d: ImproveDriver; outcome: string }) {
  const sample = sampleText(d);
  return (
    <li className="surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip">{d.grade === "clear" ? "Clear association" : "Early hint"}</span>
        <span className="chip">association, not proof</span>
      </div>
      <p className="mt-3 text-paper">{driverSentence(d, outcome)}</p>
      <CiBar ci={d.ci} diff={d.diff} unit={d.unit} />
      <p className="mt-2 text-xs text-mute">
        {sample}
        {d.q != null && ` · q = ${d.q.toFixed(2)}`}
        {d.lag_days ? ` · ${d.lag_days} day lag` : ""}
        {d.adjusted_for?.length ? ` · adjusted for ${d.adjusted_for.join(", ")}` : ""}
      </p>
      {d.grade === "hint" && <p className="mt-1 text-xs text-mute">Early, based on {d.n_exposed ?? "few"} nights; could easily be chance.</p>}
    </li>
  );
}

function StartCard({ s, cites, onOpen }: { s: ImproveStart; cites: Cites; onOpen: (id: string) => void }) {
  return (
    <li className="surface p-4">
      <p className="text-paper">{s.finding ?? s.id}</p>
      <Numbers numbers={s.numbers} />
      {s.why && <p className="mt-3 text-sm text-mute">{s.why}</p>}
      {s.action && (
        <p className="mt-3 border-l-2 border-gold pl-3 text-sm text-paper">
          <span className="text-[11px] text-dim">Worth trying for 4 weeks</span>
          <br />
          {s.action}
        </p>
      )}
      <p className="mt-2 text-xs text-mute">
        {s.timescale ? `Timescale: ${s.timescale}. ` : ""}Studies show ranges, your own result may differ · {confidenceLabel(s.confidence)}
      </p>
      <CitationChips ids={s.citations} cites={cites} onOpen={onOpen} />
    </li>
  );
}

function WatchCard({ w, cites, onOpen }: { w: ImproveWatch; cites: Cites; onOpen: (id: string) => void }) {
  return (
    <li className={clsx("surface border-l-2 p-4", w.severity === "act" ? "!border-l-amber" : "!border-l-gold")}>
      <p className="flex items-center gap-2 text-paper">
        <Eye size={14} className="text-gold" aria-hidden /> {watchLabel(w)}
      </p>
      <Numbers numbers={w.numbers} />
      {w.suggestion && <p className="mt-3 text-sm text-mute">{w.suggestion}</p>}
      <p className="mt-2 text-xs text-dim">A prompt to look, based on your own baseline. Not a diagnosis; if you feel unwell, speak to a clinician.</p>
      <CitationChips ids={w.citations} cites={cites} onOpen={onOpen} />
    </li>
  );
}

function Benchmark({ metric, b, unit }: { metric: string; b: ImproveBenchmark; unit?: string }) {
  return (
    <li className="border border-line p-4 text-sm text-mute">
      <p className="text-[11px] text-dim">{metric.replace(/_/g, " ")} · context only</p>
      <p className="mt-1">
        {b.value != null && <span className="num text-lg text-mute">{b.value}{unit ? ` ${unit}` : ""} </span>}
        {b.band && <span>band: {b.band}</span>}
        {b.personal_band && <span>your usual range: {b.personal_band[0]} to {b.personal_band[1]}{unit ? ` ${unit}` : ""}</span>}
        {b.percentile && <span> · roughly the {b.percentile[0]}th to {b.percentile[1]}th percentile of people your age and sex</span>}
      </p>
      {b.caveat ? <p className="mt-1 text-xs">{b.caveat}</p> : b.estimate ? <p className="mt-1 text-xs">Garmin's estimate, not a lab measurement; wearable estimates differ from treadmill tests.</p> : null}
    </li>
  );
}

const outcomeName = (m: string) => (m === "hrv" ? "overnight HRV" : m === "resting_hr" ? "resting heart rate" : "VO2max (Garmin's estimate)");

export function ImprovePanel({ metric, report }: { metric: string; report: ImproveReport }) {
  const cites = useMemo(() => normalizeCitations(report.citations), [report.citations]);
  const statuses = sectionStatuses(report);
  const watch = orderWatch(report.watch);
  const [tab, setTab] = useState<SectionKey>("moving");
  const [cite, setCite] = useState<string | null>(null);
  const [allStarts, setAllStarts] = useState(false);
  const starts = orderStarts(report.start);
  const drivers = orderDrivers(report.drivers);
  const needed = neededText(report);
  const info = statuses.find((s) => s.key === tab)!;
  const c = cite ? cites[cite] : null;
  const bench = (Object.entries(report.benchmarks ?? {}).filter(([k, v]) => k !== "profile_missing" && v && typeof v === "object" && (v as ImproveBenchmark).value != null) as [string, ImproveBenchmark][]).sort(
    (a, b) => Number(b[0] === metric) - Number(a[0] === metric),
  );
  const base = report.baseline;

  return (
    <section id="improve" aria-label="Improve" className="space-y-4">
      <div>
        <p className="eyebrow">Improve</p>
        <p className="mt-1 text-xs text-mute">{ASSOCIATION_NOTE}</p>
      </div>

      {base?.mean != null && (
        <p className="text-sm text-mute">
          Your baseline: <span className="num text-paper">{signed(base.mean).replace("+", "")}{base.unit ? ` ${base.unit}` : ""}</span>
          {base.band && ` (usual band ${base.band[0]} to ${base.band[1]})`}
          {base.n != null && ` · n = ${base.n} days${base.window_days ? ` of the last ${base.window_days}` : ""}`}
          {base.mean_7d != null && ` · last 7 days ${base.mean_7d}${base.n_7d != null ? ` (n = ${base.n_7d})` : ""}`}
          {base.cv_7d != null && ` · 7-day variability ${base.cv_7d}%`}
        </p>
      )}

      {report.context?.length ? (
        <ul className="space-y-1 text-xs text-mute">{report.context.map((x) => <li key={x.id}>{x.text}</li>)}</ul>
      ) : null}

      {watch.length > 0 && report.state === "ready" && (
        <ul className="space-y-3">{watch.map((w) => <WatchCard key={w.id} w={w} cites={cites} onOpen={setCite} />)}</ul>
      )}

      {report.state === "collecting" && needed && (
        <Collecting label="Improve" text={`Here's what's needed: ${needed}.`} />
      )}
      {report.state === "collecting" && (report.progress?.length ?? 0) > 0 && (
        <ul className="space-y-2">
          {report.progress!.map((p) => (
            <li key={p.key} className="text-xs text-mute">
              {p.label ?? p.key.replace(/_/g, " ")}: {p.have} of {p.needed}
              <div className="mt-1 h-1 bg-line-strong" role="progressbar" aria-valuemin={0} aria-valuemax={p.needed} aria-valuenow={p.have}>
                <div className="h-1 bg-gold" style={{ width: `${progressPct(p.have, p.needed)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}

      <div role="tablist" aria-label="Improve sections" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {statuses.map((s) => (
          <button
            key={s.key}
            type="button"
            role="tab"
            aria-selected={tab === s.key}
            onClick={() => setTab(s.key)}
            className={clsx("chip min-h-11 shrink-0 normal-case tracking-normal", tab === s.key ? "!border-gold !text-paper" : "hover:text-paper")}
          >
            {SECTION_LABEL[s.key]}
            {s.count > 0 && <span className="num text-dim">{s.count}</span>}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="space-y-3">
        {tab === "moving" &&
          (drivers.length ? (
            <ul className="space-y-3">{drivers.map((d) => <DriverCard key={d.id} d={d} outcome={outcomeName(metric)} />)}</ul>
          ) : (
            <Collecting
              label={SECTION_LABEL.moving}
              text={
                needed
                  ? `Here's what's needed: ${needed}.`
                  : "Nothing stands out yet. A finding needs enough days both with and without each habit, and anything that could easily be chance is not shown."
              }
            />
          ))}
        {tab === "moving" && report.data?.missing_signals?.length ? (
          <p className="text-xs text-mute">
            Not tracked, so not tested: {report.data.missing_signals.join(", ")}. Missing is not the same as none.{" "}
            <Link to="/" className="underline hover:text-paper">Log habits in the check-in</Link>.
          </p>
        ) : null}

        {tab === "start" &&
          (starts.length ? (
            <>
              <ul className="space-y-3">
                {(allStarts ? starts : starts.slice(0, 3)).map((s) => <StartCard key={s.id} s={s} cites={cites} onOpen={setCite} />)}
              </ul>
              {starts.length > 3 && (
                <button type="button" onClick={() => setAllStarts((v) => !v)} className="chip min-h-11" aria-expanded={allStarts}>
                  <ChevronDown size={12} className={clsx(allStarts && "rotate-180")} aria-hidden /> {allStarts ? "Show fewer" : `Show ${starts.length - 3} more`}
                </button>
              )}
            </>
          ) : (
            <Collecting label={SECTION_LABEL.start} text={needed ? `Here's what's needed: ${needed}.` : "No suggestion fits your recent training right now."} />
          ))}

        {tab === "watch" &&
          (watch.length ? (
            <ul className="space-y-3">{watch.map((w) => <WatchCard key={w.id} w={w} cites={cites} onOpen={setCite} />)}</ul>
          ) : (
            <Collecting
              label={SECTION_LABEL.watch}
              text={report.state === "collecting" ? `Needs about 14 days of baseline. ${needed}` : "Nothing is worth a look right now. Time off is never counted as a miss."}
            />
          ))}

        {tab === "focus" &&
          (report.focus?.priorities?.length ? (
            <div className="surface p-4">
              <p className="eyebrow">{report.focus.proposed ? "Proposed focus" : "Current focus"}</p>
              <ol className="mt-3 space-y-3">
                {report.focus.priorities.map((p, i) => (
                  <li key={i} className="text-sm">
                    <p className="text-paper">{p.rank ?? i + 1}. {p.title}</p>
                    {p.behaviour && <p className="mt-1 text-mute">{p.behaviour}</p>}
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-xs text-mute">
                {report.focus.check_on ? `Check on ${report.focus.check_on}. ` : ""}A range is not a promise; the check compares your numbers before and after.
              </p>
              {report.focus.blocked_by && <p className="mt-2 text-xs text-amber">Paused while this is flagged: {blockedText(report.focus.blocked_by)}</p>}
            </div>
          ) : (
            <Collecting label={SECTION_LABEL.focus} text={needed ? `Here's what's needed: ${needed}.` : "A 4-week focus appears once there is enough data to rank suggestions."} />
          ))}

        {tab === "review" &&
          (report.review?.verdict ? (
            <div className="surface p-4">
              <p className="text-paper">{verdictText(report.review)}</p>
              <CiBar ci={report.review.ci} diff={report.review.change} unit={report.review.unit} />
              {report.review.context?.length ? <p className="mt-2 text-xs text-mute">Also over those weeks: {report.review.context.join(" · ")}</p> : null}
            </div>
          ) : (
            <Collecting label={SECTION_LABEL.review} text={reviewNote(report.review) ?? "Needs a finished 4-week focus with at least 14 days of data in each window. Nothing to compare yet."} />
          ))}

        {tab === "compare" &&
          (bench.length ? (
            <ul className="space-y-3">{bench.map(([k, b]) => <Benchmark key={k} metric={k} b={b} unit={k === "vo2max" ? "mL/kg/min" : k === "hrv" ? "ms" : k === "resting_hr" ? "bpm" : undefined} />)}</ul>
          ) : (
            <Collecting
              label={SECTION_LABEL.compare}
              text={report.benchmarks?.profile_missing ? "Add your age and sex in Settings to see where you sit among people like you." : "No comparison available for this metric."}
            />
          ))}
        {tab === "compare" && bench.length > 0 && (
          <p className="text-xs text-dim">Grey context from published tables. Ranges are wide, devices differ, and your own baseline matters more.</p>
        )}
        {info.status === "ready" && tab !== "compare" && <p className="text-[11px] text-dim">Association, not proof.</p>}
      </div>

      <Sheet open={cite != null} onOpenChange={(o) => !o && setCite(null)} title={c ? (c.short ?? c.title ?? cite) : (cite ?? "")} eyebrow="Source">
        {c ? (
          <div className="space-y-3 text-sm text-mute">
            {c.title && <p className="text-paper">{c.title}</p>}
            <p>{[c.authors, c.journal, c.year].filter(Boolean).join(" · ")}</p>
            {c.summary && <p>{c.summary}</p>}
            {c.quality && c.quality !== "unrated" && <p>Evidence quality: {c.quality}</p>}
            {c.verified === false && <p className="text-xs">Details not yet checked against the original source; treat as a pointer, not a finding.</p>}
            {doiUrl(c) && (
              <a href={doiUrl(c)!} target="_blank" rel="noreferrer noopener" className="chip min-h-11 hover:text-paper">Open source</a>
            )}
          </div>
        ) : (
          <p className="text-sm text-mute">Source details were not included for this reference.</p>
        )}
      </Sheet>
    </section>
  );
}

/** Improve section for a metric page. Fetches GET only, so it works on the read-only phone server. */
export function ImproveSection({ metric }: { metric: string }) {
  const query = useQuery({ queryKey: ["improve", metric], queryFn: () => api.improve(metric), retry: 1 });
  if (query.isPending) return <div className="h-40 animate-pulse bg-coal" aria-label="Loading Improve" />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const r = query.data;
  if (r.state === "error") return <div className="surface p-4 text-sm text-mute">Improve could not be computed. {r.message ?? ""}</div>;
  if (r.state === "unsupported")
    return (
      <div className="surface p-4 text-sm text-mute">
        <p className="eyebrow mb-1">Improve</p>
        {r.message ?? "Your device does not report this metric, so there is nothing to analyse."}
      </div>
    );
  return <ImprovePanel metric={metric} report={r} />;
}

/** Compact Home card: top priority or an active watch flag. Hidden when there is nothing to say. */
export function ImproveHomeCard() {
  const query = useQuery({ queryKey: ["improve-summary"], queryFn: api.improveSummary, retry: 1 });
  if (query.isPending || query.isError) return null; // optional extra: never blocks or breaks Home
  const card = homeCard(query.data);
  if (!card) return null;
  const metric = card.metric && ["hrv", "resting_hr", "vo2max"].includes(card.metric) ? card.metric : "hrv";
  return (
    <Link to={`/metrics/${metric}#improve`} className="surface surface-hover block min-h-11 p-4">
      <p className="eyebrow flex items-center gap-2">
        <Compass size={12} className="text-gold" aria-hidden /> {card.kind === "watch" ? "Worth a look" : "Focus this month"}
      </p>
      <p className="mt-2 text-paper">{card.text}</p>
      {card.kind === "focus" && card.detail && <p className="mt-1 text-sm text-mute">{card.detail}</p>}
      <p className="mt-2 text-xs text-dim">
        {card.kind === "focus" && card.checkOn ? `Check on ${card.checkOn} · ` : ""}Association in your own data, not proof
      </p>
    </Link>
  );
}
