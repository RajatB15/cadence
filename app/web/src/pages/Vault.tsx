import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Archive, CircleStop, DatabaseZap, Download, FileSearch, RefreshCw, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CountUp } from "../components/CountUp";
import { FieldGrid, JsonTree, humanize } from "../components/DataViews";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate, parseDay } from "../lib/format";
import type { GarminDataset, GarminStatus, VaultItemMeta } from "../lib/types";

const STATUS: Record<GarminDataset["status"], { text: string; className: string }> = {
  complete: { text: "Full history", className: "!border-lime/40 !text-lime" },
  synced: { text: "Archived", className: "!border-lime/40 !text-lime" },
  backfilling: { text: "Backfilling", className: "!border-gold/50 !text-gold" },
  pending: { text: "Queued", className: "" },
  unavailable: { text: "Not on account", className: "!text-dim" },
};

const RUN_TEXT: Record<string, string> = {
  succeeded: "Up to date",
  partial: "Partly synced",
  paused: "Paused by Garmin rate limit",
  stopped: "Stopped",
  failed: "Failed",
  interrupted: "Interrupted · resumes on next sync",
};

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

export function VaultPage() {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["garmin-status"],
    queryFn: api.garminStatus,
    refetchInterval: (q) => (q.state.data?.busy ? 1000 : 15000),
  });
  const wasBusy = useRef(false);
  useEffect(() => {
    const busy = status.data?.busy ?? false;
    // Refresh dashboards as data lands and once more when the job settles.
    if (busy || wasBusy.current) {
      client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "garmin-status" });
    }
    wasBusy.current = busy;
  }, [status.data, client]);

  const onSettled = () => client.invalidateQueries({ queryKey: ["garmin-status"] });
  const sync = useMutation({ mutationFn: api.garminSync, onSettled });
  const stop = useMutation({ mutationFn: api.garminStop, onSettled });
  const rebuild = useMutation({ mutationFn: api.garminRebuild, onSettled });

  if (status.isPending) return <LoadingBlock height={560} />;
  if (status.isError) return <ErrorBlock error={status.error} retry={() => status.refetch()} />;
  const s = status.data;
  const actionError = [sync, stop, rebuild].find((m) => m.isError)?.error;

  return (
    <>
      <PageHeader
        eyebrow={<><Archive size={12} /> Garmin vault · stored on this Mac</>}
        title={<>Your history, <em className="text-gold">kept forever.</em></>}
      >
        {s.busy ? (
          <button type="button" className="pop pop-coral" onClick={() => stop.mutate()} disabled={stop.isPending}>
            <CircleStop size={16} /> Stop
          </button>
        ) : (
          <>
            <button type="button" className="pop pop-ghost" onClick={() => sync.mutate("quick")}>
              <RefreshCw size={16} /> Quick sync
            </button>
            <button type="button" className="pop pop-lime" onClick={() => sync.mutate("full")}>
              <Sparkles size={16} /> Sync everything
            </button>
          </>
        )}
      </PageHeader>

      {actionError && (
        <p role="alert" className="mb-6 text-sm text-coral">
          {actionError.message}
        </p>
      )}

      <Hero s={s} />
      <RunStrip s={s} />

      <section className="mt-12 grid gap-4 lg:grid-cols-3">
        <div className="surface p-7 lg:col-span-2">
          <div className="mb-6 flex items-baseline justify-between">
            <h2 className="font-display text-3xl text-cream">Coverage</h2>
            <p className="eyebrow">Each line reaches back to its first record</p>
          </div>
          <Coverage datasets={s.datasets} firstDay={s.totals.first_day} />
        </div>
        <VaultCard s={s} busy={s.busy} onRebuild={() => rebuild.mutate()} />
      </section>

      <Explorer datasets={s.datasets.filter((d) => d.responses > 0)} />
    </>
  );
}

function Hero({ s }: { s: GarminStatus }) {
  const int = useCallback((v: number) => Math.round(v).toLocaleString(), []);
  const first = s.totals.first_day;
  const years = first ? (Date.now() - parseDay(first).getTime()) / (365.25 * 86_400_000) : 0;
  const stats = [
    { label: "Days recorded", value: s.totals.days },
    { label: "Sessions", value: s.totals.activities },
    { label: "Weigh-ins", value: s.totals.weigh_ins },
    { label: "Garmin calls, lifetime", value: s.totals.api_calls },
  ];
  return (
    <section className="relative border-y border-line py-10">
      <div className="pointer-events-none absolute top-6 right-10 h-64 w-64 rounded-full bg-gold/10 blur-3xl" />
      <p className="eyebrow mb-3">History reaches back to</p>
      <p className="font-display text-6xl leading-none text-cream sm:text-8xl">
        {first ? formatDate(first) : "—"}
      </p>
      {first && (
        <p className="mt-3 text-lg text-gold italic font-display">
          {years >= 1 ? `${years.toFixed(1)} years` : `${Math.round(years * 12)} months`} of you, in one place.
        </p>
      )}
      <div className="mt-10 grid grid-cols-2 gap-6 lg:grid-cols-4">
        {stats.map((x) => (
          <div key={x.label}>
            <p className="eyebrow mb-2">{x.label}</p>
            <CountUp value={x.value} format={int} className="num text-4xl text-paper" />
          </div>
        ))}
      </div>
    </section>
  );
}

function RunStrip({ s }: { s: GarminStatus }) {
  const run = s.run;
  if (!run) {
    return (
      <p className="mt-8 text-mute">
        Nothing synced yet. <span className="text-paper">Sync everything</span> pulls every dataset Garmin
        offers, as far back as your account goes. Each day is fetched once and stored here.
      </p>
    );
  }
  const live = s.busy;
  return (
    <motion.div
      layout
      className={clsx(
        "surface mt-8 flex flex-wrap items-center gap-x-8 gap-y-3 px-6 py-5",
        live && "border-gold/40",
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-4">
        <span className="relative grid h-3 w-3 place-items-center">
          {live && <span className="absolute h-3 w-3 animate-ping rounded-full bg-gold/60" />}
          <span
            className={clsx(
              "h-2 w-2 rounded-full",
              live ? "bg-gold" : run.status === "succeeded" ? "bg-lime" : run.status === "failed" ? "bg-coral" : "bg-amber",
            )}
          />
        </span>
        <div className="min-w-0">
          <p className="truncate font-semibold text-paper">
            {live ? run.message || "Working…" : RUN_TEXT[run.status] ?? run.status}
          </p>
          <p className="truncate text-xs text-mute">
            {run.mode === "rebuild" ? "Offline rebuild" : run.mode === "full" ? "Full sync" : "Quick sync"} ·{" "}
            started {new Date(`${run.started_at}Z`).toLocaleString()}
            {run.error && <span className="text-coral"> · {run.error}</span>}
          </p>
        </div>
      </div>
      <Stat label="Requests" value={run.requests_made ?? 0} />
      <Stat label="Records" value={run.records_written} />
      {live && (
        <div className="absolute inset-x-0 bottom-0 h-px overflow-hidden">
          <motion.div
            className="h-px w-1/3 bg-gradient-to-r from-transparent via-gold to-transparent"
            animate={{ x: ["-100%", "300%"] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
          />
        </div>
      )}
    </motion.div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-right">
      <p className="num text-2xl text-paper">{value.toLocaleString()}</p>
      <p className="text-[10px] tracking-widest text-dim uppercase">{label}</p>
    </div>
  );
}

function Coverage({ datasets, firstDay }: { datasets: GarminDataset[]; firstDay: string | null }) {
  const today = Date.now();
  const origin = firstDay ? parseDay(firstDay).getTime() : today - 365 * 86_400_000;
  const span = Math.max(today - origin, 86_400_000);
  const position = (day: string | null) =>
    day ? Math.min(100, Math.max(0, ((parseDay(day).getTime() - origin) / span) * 100)) : 100;

  return (
    <ul className="space-y-4">
      {datasets.map((d) => {
        const st = STATUS[d.status];
        const ranged = d.kind === "range";
        const left = position(d.oldest);
        return (
          <li key={d.key} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-paper">{d.label}</p>
              <p className="truncate text-[11px] text-dim">
                {d.tier === "deep" ? "Deep archive" : "Core"} · {d.responses.toLocaleString()} stored
                {d.stored_bytes > 0 && ` · ${bytes(d.stored_bytes)}`}
              </p>
            </div>
            <div className="relative h-2 bg-slate" title={d.error ?? undefined}>
              {ranged && d.oldest && (
                <motion.div
                  className={clsx("absolute inset-y-0 right-0", d.status === "complete" ? "bg-lime/70" : "bg-gold/70")}
                  initial={{ left: "100%" }}
                  animate={{ left: `${left}%` }}
                  transition={{ duration: 1, ease: [0.2, 0.9, 0.1, 1] }}
                />
              )}
              {!ranged && d.responses > 0 && <div className="absolute inset-0 bg-lime/30" />}
            </div>
            <span className={clsx("chip w-32 justify-center", st.className)}>{st.text}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Explorer({ datasets }: { datasets: GarminDataset[] }) {
  const [dataset, setDataset] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [itemId, setItemId] = useState<number | null>(null);
  const active = dataset ?? datasets[0]?.key ?? null;
  const list = useQuery({
    queryKey: ["vault-list", active, page],
    queryFn: () => api.vaultList(active!, PAGE_SIZE, page * PAGE_SIZE),
    enabled: active != null,
  });
  const item = useQuery({
    queryKey: ["vault-item", itemId],
    queryFn: () => api.vaultItem(itemId!),
    enabled: itemId != null,
  });
  if (!datasets.length) return null;
  const pages = Math.ceil((list.data?.total ?? 0) / PAGE_SIZE);

  return (
    <section className="surface mt-4 p-7">
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="flex items-center gap-3 font-display text-3xl text-cream">
          <FileSearch size={22} className="text-gold" /> Data explorer
        </h2>
        <p className="eyebrow">Every stored response, exactly as Garmin sent it</p>
      </div>
      <div className="mb-6 flex flex-wrap gap-2">
        {datasets.map((d) => (
          <button
            key={d.key}
            type="button"
            onClick={() => {
              setDataset(d.key);
              setPage(0);
              setItemId(null);
            }}
            className={clsx(
              "chip transition-colors",
              active === d.key ? "!border-cream bg-cream !text-ink" : "hover:!text-paper",
            )}
          >
            {d.label} · {d.responses.toLocaleString()}
          </button>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <div>
          <ul className="max-h-[560px] divide-y divide-line/60 overflow-auto border border-line">
            {list.data?.items.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setItemId(r.id)}
                  className={clsx(
                    "flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition-colors",
                    itemId === r.id ? "bg-slate text-paper" : "text-mute hover:bg-slate/60 hover:text-paper",
                  )}
                >
                  <span className="min-w-0 truncate">{describe(r)}</span>
                  <span className="num shrink-0 text-xs text-dim">
                    {r.is_file ? "FIT" : `${r.item_count}`} · {bytes(r.body_bytes)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {pages > 1 && (
            <div className="mt-3 flex items-center justify-between text-xs text-mute">
              <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="eyebrow disabled:opacity-30">
                ← Newer
              </button>
              <span className="num">
                {page + 1} / {pages}
              </span>
              <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)} className="eyebrow disabled:opacity-30">
                Older →
              </button>
            </div>
          )}
        </div>
        <div className="min-w-0">
          {itemId == null ? (
            <p className="py-16 text-center text-sm text-dim">Pick a response to see every field it contains.</p>
          ) : item.isPending ? (
            <LoadingBlock height={320} />
          ) : item.isError ? (
            <ErrorBlock error={item.error} />
          ) : (
            <div>
              <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-mute">
                <span className="chip">HTTP {item.data.meta.status}</span>
                <span className="chip">{item.data.meta.final ? "Settled" : "Provisional"}</span>
                <span>fetched {new Date(`${item.data.meta.fetched_at}Z`).toLocaleString()}</span>
                {item.data.activity_id && (
                  <Link to={`/activities/${item.data.activity_id}`} className="eyebrow !text-gold hover:underline">
                    Open activity →
                  </Link>
                )}
              </div>
              {item.data.meta.is_file ? (
                <p className="text-sm text-mute">
                  Original FIT recording. Decoded in full on the activity page — every channel, lap, set and message.
                </p>
              ) : item.data.payload == null ? (
                <p className="text-sm text-dim">Empty response.</p>
              ) : Array.isArray(item.data.payload) || typeof item.data.payload !== "object" ? (
                <JsonTree name={describe(item.data.meta)} value={item.data.payload} />
              ) : (
                <FieldGrid data={item.data.payload as Record<string, unknown>} />
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

const PAGE_SIZE = 50;

function describe(r: VaultItemMeta): string {
  if (r.window_start && r.window_end && r.window_start !== r.window_end) {
    return `${formatDate(r.window_start)} → ${formatDate(r.window_end)}`;
  }
  if (r.window_start) return formatDate(r.window_start);
  const [, rest] = r.request_key.split(":", 2);
  return rest ? `#${r.request_key.split(":").slice(1).join(" · ")}` : humanize(r.dataset);
}

function VaultCard({ s, busy, onRebuild }: { s: GarminStatus; busy: boolean; onRebuild: () => void }) {
  const ratio = s.vault.raw_bytes ? s.vault.raw_bytes / Math.max(1, s.vault.stored_bytes - s.vault.file_bytes) : 0;
  return (
    <div className="surface flex flex-col p-7">
      <div className="grid h-10 w-10 place-items-center bg-gold/15 text-gold">
        <DatabaseZap size={18} />
      </div>
      <h2 className="mt-5 font-display text-3xl text-cream">The vault</h2>
      <p className="mt-2 text-sm text-mute">
        Every Garmin response is kept verbatim and compressed. Dashboards are rebuilt from here, so settled
        days are never requested again.
      </p>
      <dl className="mt-6 grid grid-cols-2 gap-5">
        <div>
          <dt className="eyebrow mb-1">Responses</dt>
          <dd className="num text-2xl text-paper">{s.vault.responses.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="eyebrow mb-1">On disk</dt>
          <dd className="num text-2xl text-paper">{bytes(s.vault.stored_bytes)}</dd>
        </div>
        <div>
          <dt className="eyebrow mb-1">FIT files</dt>
          <dd className="num text-2xl text-paper">{s.vault.files.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="eyebrow mb-1">Compression</dt>
          <dd className="num text-2xl text-paper">{ratio ? `${ratio.toFixed(1)}×` : "—"}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="pop pop-ghost mt-auto self-start"
        style={{ marginTop: "2rem" }}
        disabled={busy || s.vault.responses === 0}
        onClick={onRebuild}
      >
        <Download size={16} /> Rebuild offline
      </button>
      <p className="mt-3 text-xs text-dim">Re-derives every chart from the vault with zero Garmin calls.</p>
    </div>
  );
}
