import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, CircleDot } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";
import { CRAWL_COLOR, crawlSegments, librarySegments, percent, roughDuration, type Segment } from "../lib/foodCrawl";
import type { FoodCrawlProgress } from "../lib/types";

const POLL_MS = 15_000;
const nf = new Intl.NumberFormat();
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/** One stacked bar for a set of states, with a legend that carries the numbers so colour is never the only cue. */
function StackedBar({ segments, label }: { segments: Segment[]; label: string }) {
  const total = segments.reduce((s, x) => s + x.pages, 0);
  return (
    <div>
      <div className="flex h-4 w-full gap-0.5 overflow-hidden rounded-sm" role="img" aria-label={`${label}: ${segments.map((s) => `${s.label} ${nf.format(s.pages)}`).join(", ")}`}>
        {segments.filter((s) => s.pages > 0).map((s) => (
          <div key={s.key} style={{ width: `${(s.pages / total) * 100}%`, background: s.color, minWidth: 3 }} title={`${s.label}: ${nf.format(s.pages)}`} />
        ))}
      </div>
      <ul className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-2">
        {segments.map((s) => (
          <li key={s.key} className="flex items-baseline gap-2 text-sm">
            <span className="mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: s.color }} aria-hidden />
            <span className="text-mute">{s.label}</span>
            <span className="num ml-auto text-paper">{nf.format(s.pages)}</span>
            <span className="num w-10 text-right text-dim">{percent(s.pages, total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function timelineOptions(tl: FoodCrawlProgress["timeline"]): { total: ChartOption; rate: ChartOption } {
  const tip = (rows: string[][]) => (rows.map(([k, v]) => `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:#8d8a82">${k}</span><b>${v}</b></div>`).join(""));
  const when = (v: number) => new Date(v).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
  const base = { ...chartBase, animation: false, grid: { ...chartBase.grid, left: 4, right: 12 } };
  return {
    total: {
      ...base,
      tooltip: { ...chartBase.tooltip, formatter: (p: { value: [number, number] }[]) => `${when(p[0].value[0])}${tip([["Parsed so far", nf.format(p[0].value[1])]])}` },
      yAxis: { ...chartBase.yAxis, scale: false, min: 0 },
      series: [{ type: "line", showSymbol: false, smooth: false, lineStyle: { color: CRAWL_COLOR.parsed, width: 2 }, areaStyle: { color: CRAWL_COLOR.parsed, opacity: 0.1 }, data: tl.map((r) => [new Date(r.at).getTime(), r.cumulative]) }],
    },
    rate: {
      ...base,
      tooltip: { ...chartBase.tooltip, formatter: (p: { value: [number, number] }[]) => `${when(p[0].value[0])}${tip([["Parsed in 10 min", nf.format(p[0].value[1])], ["Per minute", (p[0].value[1] / 10).toFixed(1)]])}` },
      yAxis: { ...chartBase.yAxis, scale: false, min: 0 },
      series: [{ type: "bar", barMaxWidth: 8, itemStyle: { color: CRAWL_COLOR.parsed, borderRadius: [4, 4, 0, 0] }, data: tl.map((r) => [new Date(r.at).getTime(), r.pages]) }],
    },
  };
}

export function FoodCrawlPage() {
  const query = useQuery({ queryKey: ["food-crawl"], queryFn: api.foodCrawl, refetchInterval: POLL_MS });
  const p = query.data?.progress ?? null;
  const charts = useMemo(() => (p ? timelineOptions(p.timeline) : null), [p]);

  return (
    <>
      <PageHeader
        eyebrow={<Link to="/food" className="inline-flex items-center gap-1 hover:text-paper"><ChevronLeft size={12} /> Food</Link>}
        title={<>Library <em className="text-gold">build.</em></>}
      >
        {p && (
          <span className="chip" role="status">
            <CircleDot size={12} className={query.isFetching ? "animate-pulse text-lime" : "text-mute"} /> Live · updated {clock(p.now)}
          </span>
        )}
      </PageHeader>

      {query.isLoading && <LoadingBlock height={420} />}
      {query.isError && <ErrorBlock error={query.error} retry={() => query.refetch()} />}
      {query.isSuccess && !p && (
        <div className="surface p-8 text-center">
          <p className="text-paper">The food library isn't set up on this Mac.</p>
          <p className="mt-2 text-sm text-mute">The private food-data folder with the food library crawl isn't there yet, so there is nothing to track. Your own dishes still work.</p>
        </div>
      )}

      {p && charts && (
        <div className="grid gap-6">
          <section className="surface p-6">
            <p className="eyebrow mb-2">Pages from the source</p>
            <p className="font-display text-5xl text-cream">
              <span className="num">{nf.format(p.parsed)}</span>
              <span className="text-mute"> of </span>
              <span className="num">{nf.format(p.total)}</span>
              <span className="ml-3 text-2xl text-gold">{percent(p.parsed, p.total)}</span>
            </p>
            <p className="mt-2 text-sm text-mute">
              {p.untried === 0 && p.failed === 0
                ? "Every page has been fetched."
                : p.finish && p.rate_per_min
                  ? `${nf.format(p.untried)} not tried yet. At about ${p.rate_per_min} pages a minute that is ${roughDuration(p.now, p.finish)} more, then the failed pages are retried. A rough projection.`
                  : p.workers.fetchers + (p.workers.retry ? 1 : 0) === 0
                    ? "The crawler isn't running right now. The 15-minute sync restarts it."
                    : "Measuring the pace; a finish estimate needs half an hour of fetching."}
            </p>
            <div className="mt-6">
              <StackedBar segments={crawlSegments(p)} label="Pages by state" />
            </div>
          </section>

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <section className="surface p-6">
              <p className="eyebrow mb-1">Parsed over the last day</p>
              {p.timeline.length < 2 ? (
                <p className="py-10 text-center text-sm text-mute">Not enough history to draw yet.</p>
              ) : (
                <Chart option={charts.total} height={220} label="Pages parsed so far, over the last day" />
              )}
              <p className="eyebrow mb-1 mt-4">Pace, per 10 minutes</p>
              {p.timeline.length >= 2 && <Chart option={charts.rate} height={160} label="Pages parsed in each ten-minute period" />}
            </section>

            <section className="surface p-6">
              <p className="eyebrow mb-3">Right now</p>
              <dl className="grid gap-3 text-sm">
                <Row k="Fetchers running" v={String(p.workers.fetchers)} />
                <Row k="Retry runner" v={p.workers.retry ? "running" : "idle"} />
                <Row k="Pace, last hour" v={p.rate_per_min == null ? "measuring" : `${p.rate_per_min} pages/min`} />
                <Row k="Finish (rough)" v={p.finish ? new Date(p.finish).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "not yet known"} />
              </dl>
              <p className="eyebrow mb-3 mt-6">Why pages failed</p>
              {p.failed_reasons.length === 0 ? (
                <p className="text-sm text-mute">No failed pages.</p>
              ) : (
                <dl className="grid gap-2 text-sm">
                  {p.failed_reasons.map((r) => <Row key={r.reason} k={r.reason} v={nf.format(r.pages)} />)}
                </dl>
              )}
              <p className="mt-3 text-xs text-dim">Most are the site answering "busy" (503) once; they load on a later try.</p>
            </section>
          </div>

          <section className="surface p-6">
            <p className="eyebrow mb-3">What the parsed pages became</p>
            {!p.library || !librarySegments(p.library) ? (
              <p className="text-sm text-mute">The library hasn't been built yet. It is rebuilt every 15 minutes.</p>
            ) : (
              <>
                <StackedBar segments={librarySegments(p.library)!} label="What parsed pages became" />
                {p.library.dropped.length > 0 && (
                  <p className="mt-4 text-xs text-dim">Dropped: {p.library.dropped.map((d) => `${d.reason} (${d.pages})`).join(", ")}.</p>
                )}
                <p className="mt-2 text-xs text-dim">
                  As of the last build, from {nf.format(p.library.pages ?? 0)} pages. {nf.format(p.library.with_portion ?? 0)} dishes have a household portion; every dish is marked as a recipe-based estimate, not a measurement.
                </p>
              </>
            )}
          </section>

          <details className="surface p-6">
            <summary className="cursor-pointer text-sm text-mute">Show as a table</summary>
            <table className="num mt-4 w-full text-sm">
              <thead><tr className="text-left text-mute"><th className="py-1 font-normal">Time</th><th className="py-1 text-right font-normal">Parsed in 10 min</th><th className="py-1 text-right font-normal">Total parsed</th></tr></thead>
              <tbody>
                {[...p.timeline].reverse().slice(0, 36).map((r) => (
                  <tr key={r.at} className="border-t border-line"><td className="py-1">{new Date(r.at).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })}</td><td className="py-1 text-right">{r.pages}</td><td className="py-1 text-right">{nf.format(r.cumulative)}</td></tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      )}
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-mute">{k}</dt>
      <dd className="num text-paper">{v}</dd>
    </div>
  );
}
