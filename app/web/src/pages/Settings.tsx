import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Archive, Bell, Bluetooth, Database, KeyRound, RefreshCw, ShieldCheck, Smartphone, Trash2, Watch } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { formatDate, parseDay } from "../lib/format";
import { currentSubscription, disablePush, enablePush, pushSupport } from "../lib/push";
import { useCredentialStatus } from "../lib/useCredentialStatus";
import type { CredentialStatus, ShareStatus, SourceInfo } from "../lib/types";

const LEVEL_LABEL: Record<CredentialStatus["level"], { text: string; className: string }> = {
  ok: { text: "Within expiry", className: "!border-lime/40 !text-lime" },
  notice: { text: "Renew soon", className: "!border-gold/50 !text-gold" },
  warning: { text: "Renew this week", className: "!border-amber/50 !text-amber" },
  critical: { text: "Expires tomorrow", className: "!border-coral/60 !text-coral" },
  expired: { text: "Expired", className: "!border-coral/60 !text-coral" },
  missing: { text: "Not configured", className: "" },
  invalid_expiry: { text: "Expiry unreadable", className: "!border-amber/50 !text-amber" },
};

export function SettingsPage() {
  return (
    <>
      <PageHeader eyebrow="Control room" title={<>Settings &amp; <em className="text-gold">sources.</em></>} />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <CredentialCard />
        </div>
        <div className="lg:col-span-2">
          <PrivacyCard />
        </div>
        <div className="lg:col-span-5">
          <NotificationsCard />
        </div>
        {!READ_ONLY && (
          <div className="lg:col-span-5">
            <ShareCard />
          </div>
        )}
        <div className="lg:col-span-5">
          <WeatherCard />
        </div>
        <div className="lg:col-span-5">
          <ScaleCard />
        </div>
        <div className="lg:col-span-5">
          <SourcesCard />
        </div>
      </div>
    </>
  );
}

function WeatherCard() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["weather-setting"], queryFn: api.weatherSetting });
  const toggle = useMutation({
    mutationFn: (on: boolean) => api.setWeather(on),
    onSuccess: () => ["weather-setting", "insights", "overview", "planner-options"].forEach((k) => client.invalidateQueries({ queryKey: [k] })),
  });
  if (q.isPending) return <LoadingBlock height={160} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  return (
    <section className="surface flex flex-wrap items-start justify-between gap-6 p-8">
      <div className="max-w-2xl">
        <h2 className="font-display text-3xl text-cream">Weather context</h2>
        <p className="mt-3 text-sm leading-relaxed text-mute">
          Heat makes the same effort slower, so Cadence learns your personal heat cost and adjusts efficiency trends, labels hot sessions and
          forecasts conditions for planned runs and rides. Weather comes from Open-Meteo (free, no account). Only your location rounded to
          about 10 km and the dates are sent: never routes, times of day or any health data.
        </p>
        {!q.data.available && <p className="mt-2 text-xs text-dim">Weather requests are turned off for this server.</p>}
      </div>
      <button type="button" role="switch" aria-checked={q.data.enabled} disabled={READ_ONLY || toggle.isPending}
        onClick={() => toggle.mutate(!q.data.enabled)} className={q.data.enabled ? "pop pop-lime" : "pop pop-ghost"}>
        {q.data.enabled ? "On" : "Off"}
      </button>
    </section>
  );
}

function ScaleCard() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["scale-status"], queryFn: api.scaleStatus, refetchInterval: (x) => (x.state.data?.enabled ? 4000 : false) });
  const toggle = useMutation({
    mutationFn: (on: boolean) => api.setScale(on),
    onSuccess: () => ["scale-status", "weight", "overview", "sources"].forEach((k) => client.invalidateQueries({ queryKey: [k] })),
  });
  if (q.isPending) return <LoadingBlock height={160} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  const s = q.data;
  const state = !s.available ? "Not installed on this machine" : s.connected ? "Connected — listening for a reading" : s.enabled ? "Scanning for the scale…" : "Off";
  return (
    <section className="surface flex flex-wrap items-start justify-between gap-6 p-8">
      <div className="max-w-2xl">
        <h2 className="font-display text-3xl text-cream">Bluetooth scale</h2>
        <p className="mt-3 text-sm leading-relaxed text-mute">
          Weight from the SSW526 (Dr Trust USA 526 Legend) is read locally over Bluetooth and added to your weight trend — a reading is
          accepted once it locks on the scale's display. Body composition isn't sent by this scale and is never imported; see the research
          notes if you're curious why.
        </p>
        <p className={clsx("mt-2 text-sm", s.connected ? "text-lime" : "text-dim")}>{state}</p>
        {!s.available && <p className="mt-2 text-xs text-dim">Install the research package alongside this backend to turn this on (see the README).</p>}
        {s.last_error && <p className="mt-2 text-xs text-coral">{s.last_error}</p>}
        {s.last_reading && (
          <p className="mt-2 text-xs text-dim">
            Last reading: {s.last_reading.weight_kg.toFixed(2)} kg on {s.last_reading.local_date}
          </p>
        )}
      </div>
      <button type="button" role="switch" aria-checked={s.enabled} disabled={READ_ONLY || !s.available || toggle.isPending}
        onClick={() => toggle.mutate(!s.enabled)} className={s.enabled ? "pop pop-lime" : "pop pop-ghost"}>
        {s.enabled ? "On" : "Off"}
      </button>
    </section>
  );
}

function CredentialCard() {
  const query = useCredentialStatus();
  if (query.isPending) return <LoadingBlock height={360} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const s = query.data;
  const label = LEVEL_LABEL[s.level];

  return (
    <section className="surface h-full p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-gold/15 text-gold">
            <KeyRound size={18} />
          </div>
          <div>
            <h2 className="font-semibold text-paper">Garmin API key</h2>
            <p className="text-xs text-mute">Stored locally · never sent to this browser</p>
          </div>
        </div>
        <span className={clsx("chip", label.className)}>{label.text}</span>
      </div>

      {s.expires_on ? (
        <>
          <div className="mt-10 flex flex-wrap items-end gap-x-12 gap-y-6">
            <div>
              <p className="eyebrow mb-2">Expires</p>
              <p className="font-display text-5xl text-cream">{formatDate(s.expires_on)}</p>
            </div>
            <div>
              <p className="eyebrow mb-2">{(s.days_remaining ?? 0) > 0 ? "Days left" : "Days overdue"}</p>
              <p className="num text-5xl text-paper">{Math.abs(s.days_remaining ?? 0)}</p>
            </div>
          </div>
          <ReminderTimeline status={s} />
          <p className="mt-6 text-xs text-dim">
            Expiry is the date you recorded, not confirmed by Garmin. To renew, replace the key and
            expiry date together in the local secrets file; reminders reset automatically.
          </p>
        </>
      ) : (
        <p className="mt-8 text-sm text-mute">
          {s.level === "missing"
            ? "No key found. Add GARMIN_API_KEY to the local secrets file."
            : "Set GARMIN_API_KEY_EXPIRES_ON (YYYY-MM-DD) to enable renewal reminders."}
        </p>
      )}
    </section>
  );
}

function ReminderTimeline({ status }: { status: CredentialStatus }) {
  const expires = parseDay(status.expires_on!);
  const today = parseDay(status.today);
  const span = Math.max(...status.thresholds, 30) + 5;
  const pos = (d: Date) => {
    const daysBefore = Math.max(0, (expires.getTime() - d.getTime()) / 86_400_000);
    // Square-root scale gives the final days room to breathe.
    return Math.min(100, Math.max(0, 100 - Math.sqrt(daysBefore / span) * 100));
  };
  const todayPos = pos(today);
  const outOfWindow = (status.days_remaining ?? 0) > span;

  return (
    <div className="mt-12">
      <p className="eyebrow mb-8">Reminder schedule</p>
      <div className="relative mx-2 h-16">
        <div className="absolute top-3 right-0 left-0 h-px bg-line-strong" />
        <motion.div
          className="absolute top-3 left-0 h-px bg-gold"
          initial={{ width: 0 }}
          animate={{ width: `${todayPos}%` }}
          transition={{ duration: 1.2, ease: [0.2, 0.9, 0.1, 1] }}
        />
        {status.reminder_dates.map((d, i) => {
          const passed = parseDay(d) <= today;
          return (
            <div key={d} className="absolute -translate-x-1/2 text-center" style={{ left: `${pos(parseDay(d))}%` }}>
              <div className={clsx("mx-auto h-[25px] w-px", passed ? "bg-gold" : "bg-line-strong")} />
              <p className={clsx("num mt-1 text-xs", passed ? "text-gold" : "text-mute")}>
                {status.thresholds[i]}d
              </p>
            </div>
          );
        })}
        <div className="absolute right-0 translate-x-1/2 text-center">
          <div className="mx-auto mt-1 h-4 w-4 rotate-45 border-2 border-coral bg-ink" />
          <p className="mt-1 text-xs text-coral">Expiry</p>
        </div>
        {!outOfWindow && (
          <div className="absolute -top-6 -translate-x-1/2" style={{ left: `${todayPos}%` }}>
            <span className="bg-cream px-1.5 py-0.5 text-[10px] font-bold tracking-widest text-ink uppercase">
              Today
            </span>
          </div>
        )}
      </div>
      <p className="mt-2 text-sm text-mute">
        {outOfWindow
          ? `First reminder on ${formatDate(status.reminder_dates[0])}. You'll see a banner here and on Overview.`
          : "Each step escalates the banner; dismissing one never hides the next."}
      </p>
    </div>
  );
}

function NotificationsCard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["push"], queryFn: api.push });
  const support = pushSupport();
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  useEffect(() => {
    currentSubscription().then((s) => setSubscribed(!!s), () => setSubscribed(false));
  }, []);
  const refresh = () => client.invalidateQueries({ queryKey: ["push"] });
  const enable = useMutation({
    mutationFn: () => enablePush(query.data!.public_key),
    onSuccess: () => setSubscribed(true),
    onSettled: refresh,
  });
  const disable = useMutation({ mutationFn: disablePush, onSuccess: () => setSubscribed(false), onSettled: refresh });
  const test = useMutation({ mutationFn: api.pushTest, onSettled: refresh });
  const prefs = useMutation({ mutationFn: api.pushPrefs, onSettled: refresh });
  if (query.isPending) return <LoadingBlock height={240} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const p = query.data;
  const error = enable.error ?? disable.error ?? test.error ?? prefs.error;

  return (
    <section className="surface p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-gold/15 text-gold">
            <Bell size={18} />
          </div>
          <div>
            <h2 className="font-semibold text-paper">Notifications</h2>
            <p className="text-xs text-mute">Your coach, delivered: morning call, session verdicts, bedtime nudge</p>
          </div>
        </div>
        <span className={clsx("chip", p.devices.length > 0 && "!border-lime/40 !text-lime")}>
          {p.devices.length} device{p.devices.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <div>
          <p className="eyebrow mb-3">This device</p>
          {support === "ok" ? (
            <div className="flex flex-wrap items-center gap-3">
              {subscribed ? (
                <>
                  <span className="chip !border-lime/40 !text-lime">On</span>
                  <button type="button" className="pop pop-ghost" onClick={() => disable.mutate()} disabled={disable.isPending}>
                    Turn off
                  </button>
                </>
              ) : (
                <button type="button" className="pop pop-lime" onClick={() => enable.mutate()} disabled={enable.isPending || subscribed === null}>
                  {enable.isPending ? "Asking…" : "Turn on notifications"}
                </button>
              )}
              <button type="button" className="pop pop-ghost" onClick={() => test.mutate()} disabled={test.isPending || p.devices.length === 0}>
                Send a test
              </button>
            </div>
          ) : (
            <p className="text-sm text-mute">
              {support === "install" &&
                "On iPhone, notifications only work in the Home Screen app: tap Share → Add to Home Screen, open Cadence from there, and turn them on here."}
              {support === "insecure" &&
                "This address isn't HTTPS, so the browser won't allow notifications. Open Cadence through your Tailscale https:// address (see On your iPhone)."}
              {support === "unsupported" && "This browser doesn't support push notifications."}
            </p>
          )}
          {test.data && <p className="mt-3 text-sm text-lime">Delivered to {test.data.delivered} device{test.data.delivered === 1 ? "" : "s"}.</p>}
          {error && <p className="mt-3 text-sm text-coral">{error.message}</p>}

          {p.devices.length > 0 && (
            <ul className="mt-6 space-y-2 text-sm">
              {p.devices.map((d, i) => (
                <li key={i} className="flex justify-between gap-3 text-mute">
                  <span className="text-paper">{d.label}</span>
                  <span className="text-xs text-dim">{d.last_sent_at ? `last sent ${new Date(d.last_sent_at + "Z").toLocaleString()}` : "nothing sent yet"}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className="eyebrow mb-3">Send me</p>
          <ul className="space-y-2">
            {Object.entries(p.labels).map(([key, label]) => {
              const on = p.prefs[key];
              return (
                <li key={key}>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={on}
                    onClick={() => prefs.mutate({ ...p.prefs, [key]: !on })}
                    className="flex w-full items-center justify-between gap-4 border border-line px-4 py-3 text-left text-sm hover:border-line-strong"
                  >
                    <span className={on ? "text-paper" : "text-dim"}>{label}</span>
                    <span className={clsx("relative h-5 w-9 shrink-0 transition-colors", on ? "bg-lime" : "bg-slate")}>
                      <span className={clsx("absolute top-0.5 h-4 w-4 bg-ink transition-all", on ? "left-[18px]" : "left-0.5")} />
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-xs text-dim">
            {p.scheduler
              ? `Garmin syncs every ${p.sync_every_h} h (every 45 min on mornings until your readiness is in). Each notification is sent once.`
              : "The background scheduler is off, so nothing is sent automatically."}
          </p>
        </div>
      </div>

      {p.recent.length > 0 && (
        <div className="mt-8 border-t border-line pt-6">
          <p className="eyebrow mb-3">Recently sent</p>
          <ul className="space-y-2 text-sm">
            {p.recent.slice(0, 5).map((r, i) => (
              <li key={i} className="flex flex-wrap justify-between gap-x-4 text-mute">
                <span>
                  <span className="text-paper">{r.title}</span> · {r.body}
                </span>
                <span className="text-xs text-dim">{new Date(r.sent_at + "Z").toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function ShareCard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["share"], queryFn: api.share });
  const onSuccess = (s: ShareStatus) => client.setQueryData(["share"], s);
  const start = useMutation({ mutationFn: api.shareStart, onSuccess });
  const stop = useMutation({ mutationFn: api.shareStop, onSuccess });
  const reset = useMutation({ mutationFn: api.shareReset, onSuccess });
  if (query.isPending) return <LoadingBlock height={220} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const s = query.data;
  const error = start.error ?? stop.error ?? reset.error;

  return (
    <section className="surface p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-violet/15 text-violet">
            <Smartphone size={18} />
          </div>
          <div>
            <h2 className="font-semibold text-paper">On your iPhone</h2>
            <p className="text-xs text-mute">Read-only · Wi-Fi or Tailscale · paired by QR code</p>
          </div>
        </div>
        <span className={clsx("chip", s.running && "!border-lime/40 !text-lime")}>{s.running ? "Sharing" : "Off"}</span>
      </div>

      {s.running && s.qr && s.pair_url ? (
        <div className="mt-8 grid items-start gap-8 md:grid-cols-[auto_1fr]">
          <QrCode matrix={s.qr} label="Pairing QR code" />
          <div>
            <ol className="space-y-3 text-sm text-mute">
              <li>
                <span className="num mr-2 text-gold">1</span>
                {s.secure ? "Open the Tailscale app on your iPhone and make sure it's connected." : "Join the same Wi-Fi as this Mac."}
              </li>
              <li><span className="num mr-2 text-gold">2</span>Point the Camera at the code and open the link.</li>
              <li><span className="num mr-2 text-gold">3</span>In Safari tap Share → <span className="text-paper">Add to Home Screen</span>, open Cadence from there, and turn on notifications in Settings.</li>
            </ol>
            {!s.secure && (
              <p className="mt-6 border-l-2 border-gold/60 pl-3 text-xs text-mute">
                For access away from home and for notifications, install Tailscale on this Mac and your iPhone, then run{" "}
                <span className="num text-paper">tailscale serve --bg {s.port}</span> on the Mac. This page will switch to the
                https:// address automatically.
              </p>
            )}
            <p className="mt-6 text-xs text-dim">
              After pairing, open <span className="num text-mute">{s.urls.join(" or ")}</span>. Your phone works whenever this Mac is
              awake and Cadence is running. If macOS asks to allow incoming connections for Python, choose Allow.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button type="button" className="pop pop-coral" onClick={() => stop.mutate()} disabled={stop.isPending}>
                Stop sharing
              </button>
              <button type="button" className="pop pop-ghost" onClick={() => reset.mutate()} disabled={reset.isPending}>
                New pairing code
              </button>
            </div>
            <p className="mt-3 text-xs text-dim">A new code unpairs every phone that used the old one.</p>
          </div>
        </div>
      ) : (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-6">
          <p className="max-w-2xl text-sm text-mute">
            {s.running
              ? "Sharing is on, but no network address was found. Check that this Mac is connected to Wi-Fi."
              : "Opens a read-only copy of Cadence on your local network. Every request needs the pairing key from the QR code; nothing can be changed from the phone."}
          </p>
          {!s.running && (
            <button type="button" className="pop pop-lime" onClick={() => start.mutate()} disabled={start.isPending}>
              {start.isPending ? "Starting…" : "Share to iPhone"}
            </button>
          )}
        </div>
      )}
      {error && <p className="mt-4 text-sm text-coral">{error.message}</p>}
      {s.web_built_at && (
        <p className="mt-6 border-t border-line pt-4 text-xs text-dim">
          Phone build from {new Date(s.web_built_at * 1000).toLocaleString()}. After updating Cadence, run{" "}
          <span className="num text-mute">npm run build</span> in app/web so the phone gets the latest version.
        </p>
      )}
    </section>
  );
}

function QrCode({ matrix, label }: { matrix: number[][]; label: string }) {
  const quiet = 4;
  const size = matrix.length + quiet * 2;
  const path = matrix
    .flatMap((row, y) => row.map((cell, x) => (cell ? `M${x + quiet} ${y + quiet}h1v1h-1z` : "")))
    .join("");
  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label} className="h-56 w-56 bg-white" shapeRendering="crispEdges">
      <path d={path} fill="#0b0b0c" />
    </svg>
  );
}

function PrivacyCard() {
  return (
    <section className="surface h-full p-8">
      <div className="grid h-10 w-10 place-items-center bg-lime/10 text-lime">
        <ShieldCheck size={18} />
      </div>
      <h2 className="mt-5 font-display text-3xl text-cream">Private by construction</h2>
      <ul className="mt-5 space-y-3 text-sm text-mute">
        <li>Service listens on 127.0.0.1 only and rejects foreign hosts.</li>
        <li>Phone access is opt-in, read-only, and needs a QR pairing key.</li>
        <li>Changes require a same-origin request header, blocking cross-site writes.</li>
        <li>Data lives in a local SQLite file you can back up or delete.</li>
        <li>No analytics, no accounts, no cloud.</li>
      </ul>
    </section>
  );
}

const SOURCE_ICON = { demo: Database, garmin: Watch, scale: Bluetooth } as const;
const SOURCE_STATUS: Record<string, { text: string; className: string }> = {
  ready: { text: "Ready", className: "!border-lime/40 !text-lime" },
  empty: { text: "Empty", className: "" },
  awaiting_docs: { text: "Awaiting API docs", className: "!border-gold/40 !text-gold" },
  not_synced: { text: "Ready to connect", className: "!border-gold/40 !text-gold" },
  not_configured: { text: "No key", className: "" },
  connected: { text: "Connected", className: "!border-lime/40 !text-lime" },
  listening: { text: "Listening", className: "!border-gold/40 !text-gold" },
  off: { text: "Off", className: "" },
  unavailable: { text: "Not available", className: "" },
};

function SourcesCard() {
  const client = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.syncRuns });
  const sync = useMutation({ mutationFn: api.syncDemo, onSettled: () => client.invalidateQueries() });

  if (sources.isPending) return <LoadingBlock height={300} />;
  if (sources.isError) return <ErrorBlock error={sources.error} retry={() => sources.refetch()} />;

  return (
    <section className="surface p-8">
      <h2 className="font-display text-3xl text-cream">Data sources</h2>
      <ul className="mt-6 divide-y divide-line">
        {sources.data.map((s) => (
          <SourceRow key={s.id} s={s}>
            {s.id === "garmin" && s.status !== "not_configured" && (
              <Link to="/vault" className="pop pop-lime">
                <Archive size={14} /> Open vault
              </Link>
            )}
            {s.id === "demo" && (
              <div className="flex flex-wrap gap-4">
                <button
                  type="button"
                  className="pop pop-ghost"
                  disabled={sync.isPending}
                  onClick={() => sync.mutate()}
                >
                  <RefreshCw size={14} className={clsx(sync.isPending && "animate-spin")} />
                  {s.status === "ready" ? "Re-import" : "Import"}
                </button>
                {s.status === "ready" && <DeleteDemo />}
              </div>
            )}
          </SourceRow>
        ))}
      </ul>

      <h3 className="eyebrow mt-10 mb-3">Recent imports</h3>
      {runs.data?.length ? (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-dim">
            <tr>
              <th className="py-2 font-medium">Started</th>
              <th className="py-2 font-medium">Source</th>
              <th className="py-2 font-medium">Status</th>
              <th className="py-2 text-right font-medium">Records</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {runs.data.map((r) => (
              <tr key={r.id}>
                <td className="py-2.5 text-mute">{new Date(`${r.started_at}Z`).toLocaleString()}</td>
                <td className="py-2.5 text-paper capitalize">{r.source_id}</td>
                <td className={clsx("py-2.5", r.status === "failed" ? "text-coral" : "text-lime")}>
                  {r.status}
                  {r.error && <span className="text-dim"> · {r.error}</span>}
                </td>
                <td className="num py-2.5 text-right text-paper">{r.records_written.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-dim">No imports yet.</p>
      )}
    </section>
  );
}

function SourceRow({ s, children }: { s: SourceInfo; children?: React.ReactNode }) {
  const Icon = SOURCE_ICON[s.id as keyof typeof SOURCE_ICON] ?? Database;
  const status = SOURCE_STATUS[s.status] ?? { text: s.status, className: "" };
  return (
    <li className="flex flex-wrap items-center gap-5 py-5">
      <div className="grid h-10 w-10 place-items-center border border-line-strong text-cream">
        <Icon size={18} strokeWidth={1.75} />
      </div>
      <div className="min-w-[220px] flex-1">
        <div className="flex items-center gap-3">
          <p className="font-semibold text-paper">{s.name}</p>
          <span className={clsx("chip", status.className)}>{status.text}</span>
        </div>
        <p className="mt-1 text-sm text-mute">{s.detail}</p>
        {s.last_synced_at && (
          <p className="mt-1 text-xs text-dim">Last import {new Date(`${s.last_synced_at}Z`).toLocaleString()}</p>
        )}
      </div>
      {children}
    </li>
  );
}

function DeleteDemo() {
  const client = useQueryClient();
  const del = useMutation({ mutationFn: api.deleteDemo, onSuccess: () => client.invalidateQueries() });
  return (
    <Dialog.Root>
      <Dialog.Trigger className="pop pop-coral">
        <Trash2 size={14} /> Delete
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="surface fixed top-1/2 left-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 p-8">
          <Dialog.Title className="font-display text-4xl text-cream">Delete demo data?</Dialog.Title>
          <Dialog.Description className="mt-3 text-sm text-mute">
            Removes all synthetic metrics, sessions, weigh-ins, and import history. Your goal and
            other settings stay. You can re-import anytime.
          </Dialog.Description>
          <div className="mt-10 flex flex-wrap gap-5">
            <Dialog.Close asChild>
              <button type="button" className="pop pop-coral" onClick={() => del.mutate()}>
                Delete demo data
              </button>
            </Dialog.Close>
            <Dialog.Close className="pop pop-ghost">Cancel</Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
