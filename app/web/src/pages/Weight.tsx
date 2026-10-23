import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Target, X } from "lucide-react";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { NoteGrid } from "../components/CoachNotes";
import { CountUp } from "../components/CountUp";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate, formatShortDate, projectionCopy } from "../lib/format";
import type { WeightResponse } from "../lib/types";

const RANGES = [
  { value: 90, label: "90D" },
  { value: 180, label: "6M" },
  { value: 365, label: "1Y" },
];

export function WeightPage() {
  const [days, setDays] = useState(180);
  const query = useQuery({ queryKey: ["weight", days], queryFn: () => api.weight(days) });

  return (
    <>
      <PageHeader eyebrow="Body composition" title={<>Weight, <em className="text-gold">smoothed.</em></>}>
        <Segmented label="Range" options={RANGES} value={days} onChange={setDays} />
        {query.data && <GoalDialog current={query.data.goal_kg} />}
      </PageHeader>
      {query.isPending ? (
        <LoadingBlock height={520} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : query.data.points.length === 0 ? (
        <p className="border-y border-line py-12 text-mute">No weigh-ins in your history yet. Readings from a Garmin scale or manual entries in Garmin Connect will appear here after a sync.</p>
      ) : (
        <WeightBody data={query.data} />
      )}
    </>
  );
}

function WeightBody({ data }: { data: WeightResponse }) {
  const kg = useCallback((v: number) => v.toFixed(1), []);
  const option = useMemo<ChartOption>(() => {
    const lower = data.points.map((p) => [p.day, +(p.trend_kg - p.band_kg).toFixed(2)]);
    const band = data.points.map((p) => [p.day, +(2 * p.band_kg).toFixed(2)]);
    const goal = data.goal_kg;
    return {
      ...chartBase,
      yAxis: {
        ...chartBase.yAxis,
        min: (v: { min: number }) => Math.floor(Math.min(v.min, goal ?? v.min) - 0.5),
        max: (v: { max: number }) => Math.ceil(Math.max(v.max, goal ?? v.max) + 0.5),
      },
      tooltip: {
        ...chartBase.tooltip,
        formatter: (items: { seriesName: string; value: [string, number]; dataIndex: number }[]) => {
          const p = data.points[items[0]?.dataIndex ?? 0];
          if (!p) return "";
          return `<div style="font-weight:600;margin-bottom:6px">${formatDate(p.day)}</div>
            <div>Trend <b style="color:#d9b26a">${p.trend_kg.toFixed(2)} kg</b> ± ${p.band_kg.toFixed(2)}</div>
            <div style="color:#8d8a82">Scale ${p.weight_kg.toFixed(2)} kg</div>`;
        },
      },
      series: [
        { type: "line", data: lower, stack: "band", symbol: "none", lineStyle: { opacity: 0 }, silent: true },
        {
          type: "line",
          data: band,
          stack: "band",
          symbol: "none",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(217,178,106,0.14)" },
          silent: true,
        },
        {
          name: "Scale",
          type: "scatter",
          data: data.points.map((p) => [p.day, p.weight_kg]),
          symbolSize: 5,
          itemStyle: { color: "rgba(236,235,230,0.35)" },
        },
        {
          name: "Trend",
          type: "line",
          data: data.points.map((p) => [p.day, p.trend_kg]),
          symbol: "none",
          smooth: 0.3,
          lineStyle: { color: "#d9b26a", width: 2.5, shadowColor: "rgba(217,178,106,0.5)", shadowBlur: 12 },
          markLine:
            data.goal_kg != null
              ? {
                  symbol: "none",
                  silent: true,
                  lineStyle: { color: "#c8f560", type: "dashed", width: 1 },
                  label: { color: "#c8f560", formatter: `Goal ${data.goal_kg} kg`, position: "insideEndTop" },
                  data: [{ yAxis: data.goal_kg }],
                }
              : undefined,
        },
      ],
    };
  }, [data]);

  const p = data.projection;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Trend weight">
          <CountUp value={data.latest_trend_kg ?? 0} format={kg} className="num text-5xl text-gold" />
          <span className="ml-2 text-mute">kg</span>
        </Stat>
        <Stat label="4-week rate">
          {data.rate_kg_per_week == null ? (
            <span className="text-mute">Not enough data</span>
          ) : (
            <>
              <span className="num text-5xl text-paper">
                {data.rate_kg_per_week > 0 ? "+" : "−"}
                {Math.abs(data.rate_kg_per_week).toFixed(2)}
              </span>
              <span className="ml-2 text-mute">kg/wk</span>
              <p className="mt-1 text-xs text-dim">± {data.rate_se_kg_per_week?.toFixed(2)} standard error</p>
            </>
          )}
        </Stat>
        <Stat label="Body fat (scale est.)">
          {data.latest_body_fat_pct == null ? (
            <span className="text-mute">—</span>
          ) : (
            <>
              <span className="num text-5xl text-paper">{data.latest_body_fat_pct.toFixed(1)}</span>
              <span className="ml-2 text-mute">%</span>
            </>
          )}
        </Stat>
        <Stat label="Goal">
          {p ? (
            <>
              <span className="num text-5xl text-lime">{p.goal_kg.toFixed(1)}</span>
              <span className="ml-2 text-mute">kg</span>
              <p className="mt-1 text-xs text-mute">
                {p.status === "on_track" && p.expected ? (
                  <>
                    ~{formatDate(p.expected)}
                    {p.earliest && p.latest && (
                      <span className="text-dim">
                        {" "}
                        ({formatShortDate(p.earliest)} – {formatShortDate(p.latest)})
                      </span>
                    )}
                  </>
                ) : (
                  projectionCopy(p.status)
                )}
              </p>
            </>
          ) : (
            <span className="text-mute">Not set</span>
          )}
        </Stat>
      </div>

      <section className="surface p-4 sm:p-6">
        <div className="mb-2 flex flex-wrap items-center gap-5 px-2 text-xs text-mute">
          <Legend color="#d9b26a" label="Trend" line />
          <Legend color="rgba(217,178,106,0.35)" label="95% band" />
          <Legend color="rgba(236,235,230,0.6)" label="Scale reading" dot />
          {data.goal_kg != null && <Legend color="#c8f560" label="Goal" line dashed />}
        </div>
        <Chart option={option} height={420} label="Weight trend chart" />
      </section>

      {data.coach.length > 0 && (
        <section>
          <p className="eyebrow mb-4">Coach on your weigh-ins</p>
          <NoteGrid notes={data.coach} compact />
        </section>
      )}

      <details className="surface group p-6 text-sm text-mute">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-paper">
          <Info size={16} className="text-gold" /> How this is calculated
        </summary>
        <div className="mt-4 max-w-3xl space-y-2 leading-relaxed">
          <p>
            The trend is a forward Kalman filter: each day it blends yesterday's estimate with today's
            reading, trusting readings less when they're noisy. Gaps widen the band because the estimate
            grows less certain without new data.
          </p>
          <p>
            The rate is a least-squares slope over the last {data.model.rate_window_days} days of readings.
            Projections only appear when that slope is clearly different from zero, and the date range uses
            ±1 standard error. Daily swings from water and food are normal and are not fat change.
          </p>
        </div>
      </details>
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="surface p-6">
      <p className="eyebrow mb-4">{label}</p>
      <div>{children}</div>
    </div>
  );
}

function Legend({ color, label, line, dot, dashed }: { color: string; label: string; line?: boolean; dot?: boolean; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      {line ? (
        <span className="h-0 w-5 border-t-2" style={{ borderColor: color, borderStyle: dashed ? "dashed" : "solid" }} />
      ) : dot ? (
        <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      ) : (
        <span className="h-3 w-5" style={{ background: color }} />
      )}
      {label}
    </span>
  );
}

function GoalDialog({ current }: { current: number | null }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(current?.toString() ?? "");
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: api.setWeightGoal,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["weight"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setOpen(false);
    },
  });
  const parsed = Number(value);
  const valid = value.trim() !== "" && Number.isFinite(parsed) && parsed >= 30 && parsed <= 300;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate(Math.round(parsed * 10) / 10);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) setValue(current?.toString() ?? "");
      }}
    >
      <Dialog.Trigger className="pop">
        <Target size={16} /> {current == null ? "Set goal" : "Edit goal"}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="surface fixed top-1/2 left-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 p-8">
          <Dialog.Close className="absolute top-4 right-4 p-1 text-mute hover:text-paper" aria-label="Close">
            <X size={18} />
          </Dialog.Close>
          <Dialog.Title className="font-display text-4xl text-cream">Target weight</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-mute">
            Used for projections only. Pick something sustainable.
          </Dialog.Description>
          <form onSubmit={submit} className="mt-8">
            <label className="eyebrow" htmlFor="goal">
              Goal (kg)
            </label>
            <input
              id="goal"
              inputMode="decimal"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-5xl text-paper outline-none focus:border-gold"
              placeholder="75.0"
              aria-invalid={value !== "" && !valid}
            />
            {value !== "" && !valid && <p className="mt-2 text-xs text-coral">Enter a weight between 30 and 300 kg.</p>}
            {save.isError && <p className="mt-2 text-xs text-coral">Couldn't save. Try again.</p>}
            <div className="mt-10 flex flex-wrap gap-5">
              <button type="submit" className="pop pop-lime" disabled={!valid || save.isPending}>
                Save goal
              </button>
              {current != null && (
                <button
                  type="button"
                  className="pop pop-ghost"
                  disabled={save.isPending}
                  onClick={() => save.mutate(null)}
                >
                  Clear
                </button>
              )}
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
