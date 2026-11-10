import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Archive, Bell, Database, KeyRound, RefreshCw, ShieldCheck, Smartphone, Sparkles, Trash2, Watch } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ErrorBlock, LoadingBlock, PageSkeleton, PageHeader, Segmented } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { formatDate, parseDay, timeAgo } from "../lib/format";
import { currentSubscription, disablePush, enablePush, pushSupport } from "../lib/push";
import { applyChoice, readChoice, type ThemeChoice } from "../lib/theme";
import { useCredentialStatus } from "../lib/useCredentialStatus";
import type { ConnectorStatus, CredentialStatus, ShareStatus, SourceInfo } from "../lib/types";
import { C } from "../lib/theme";

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
          <AppearanceCard />
        </div>
        <div className="lg:col-span-5">
          <NotificationsCard />
        </div>
        {!READ_ONLY && (
          <div className="lg:col-span-5">
            <ShareCard />
          </div>
        )}
        {!READ_ONLY && (
          <div className="lg:col-span-5">
            <ClaudeConnectorCard />
          </div>
        )}
        {!READ_ONLY && (
          <div className="lg:col-span-5">
            <GarminWorkoutsCard />
          </div>
        )}
        <div className="lg:col-span-5">
          <WeatherCard />
          <ReadingFeedCard />
        </div>
        <div className="lg:col-span-5">
          <BodyProfileCard />
        </div>
        <div className="lg:col-span-5">
          <BackupCard />
        </div>
        <div className="lg:col-span-5">
          <SourcesCard />
        </div>
      </div>
    </>
  );
}

function AppearanceCard() {
  const [choice] = useState<ThemeChoice>(() => readChoice());
  const options: { id: ThemeChoice; label: string }[] = [
    { id: "system", label: "Match device" },
    { id: "dark", label: "Dark" },
    { id: "light", label: "Light" },
  ];
  return (
    <section className="surface flex flex-wrap items-start justify-between gap-6 p-8" aria-label="Appearance">
      <div className="max-w-xl">
        <p className="eyebrow mb-2">Appearance</p>
        <p className="text-mute">Dark or light. The default follows your device. Changing it reloads the page once, and it is remembered on this device only.</p>
      </div>
      <div role="radiogroup" aria-label="Theme" className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={choice === o.id}
            onClick={() => choice !== o.id && applyChoice(o.id)}
            className={clsx("chip pointer-coarse:py-2", choice === o.id ? "!border-gold !text-gold" : "hover:text-paper")}
          >
            {o.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function GarminWorkoutsCard() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["garmin-connect"], queryFn: api.garminConnect });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [asking, setAsking] = useState(false);
  const done = () => {
    setPassword("");
    setCode("");
    setAsking(false);
    client.invalidateQueries({ queryKey: ["garmin-connect"] });
  };
  const login = useMutation({
    mutationFn: () => api.garminLogin(email, password),
    onSuccess: (r) => {
      setPassword("");
      if (r.status === "needs_code") setAsking(true);
      else done();
    },
  });
  const verify = useMutation({ mutationFn: () => api.garminCode(code), onSuccess: done, onError: () => setAsking(false) });
  const disconnect = useMutation({ mutationFn: api.garminDisconnect, onSuccess: done });
  if (q.isPending) return <LoadingBlock height={160} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  const s = q.data;
  return (
    <section className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="font-display text-3xl text-cream">Send workouts to Garmin</h2>
          <p className="mt-3 text-sm leading-relaxed text-mute">
            Optional. Planned runs and rides can be sent to your Garmin Connect calendar as structured workouts (warm-up, intervals, cool-down,
            heart-rate zone targets) and sync to your watch. This signs in the way the Garmin website does, not through the official API,
            so it can stop working when Garmin changes its login and may be against Garmin&apos;s terms. It only creates and removes the
            workouts Cadence sends: it never reads or changes your activities or health data. Your password is used once and never stored;
            only a session token stays on this computer.
          </p>
        </div>
        {s.connected && <span className="chip !border-lime/40 !text-lime">Connected</span>}
      </div>
      {!s.available ? (
        <p className="mt-4 text-sm text-dim">Not installed on this server. Run <code>pip install &apos;garminconnect&gt;=0.3.20&apos;</code> in the backend environment.</p>
      ) : s.connected ? (
        <button type="button" className="pop pop-ghost mt-5" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>Disconnect</button>
      ) : asking ? (
        <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
          <label className="text-xs text-dim">Code from Garmin (email or app)
            <input className="mt-1 block w-64 max-w-full border-b-2 border-line-strong bg-transparent py-2 text-base text-paper outline-none focus:border-gold" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          <button type="submit" className="pop pop-lime" disabled={verify.isPending || code.trim().length < 4}>Verify</button>
        </form>
      ) : (
        <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); login.mutate(); }}>
          <label className="text-xs text-dim">Garmin email
            <input className="mt-1 block w-64 max-w-full border-b-2 border-line-strong bg-transparent py-2 text-base text-paper outline-none focus:border-gold" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="text-xs text-dim">Garmin password
            <input className="mt-1 block w-64 max-w-full border-b-2 border-line-strong bg-transparent py-2 text-base text-paper outline-none focus:border-gold" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button type="submit" className="pop pop-lime" disabled={login.isPending || !email || !password}>{login.isPending ? "Signing in…" : "Connect"}</button>
        </form>
      )}
      {(login.isError || verify.isError || disconnect.isError) && (
        <p className="mt-3 text-sm text-coral">{((login.error ?? verify.error ?? disconnect.error) as Error).message}</p>
      )}
    </section>
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
      <button type="button" role="switch" aria-checked={q.data.enabled} disabled={toggle.isPending || READ_ONLY}
        onClick={() => toggle.mutate(!q.data.enabled)} className={q.data.enabled ? "pop pop-lime" : "pop pop-ghost"}>
        {q.data.enabled ? "On" : "Off"}
      </button>
    </section>
  );
}

function ReadingFeedCard() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["reading-feed-setting"], queryFn: api.readingFeedSetting });
  const toggle = useMutation({
    mutationFn: (on: boolean) => api.setReadingFeed(on),
    onSuccess: () => ["reading-feed-setting", "reading"].forEach((k) => client.invalidateQueries({ queryKey: [k] })),
  });
  if (q.isPending) return <LoadingBlock height={160} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  return (
    <section className="surface flex flex-wrap items-start justify-between gap-6 p-8">
      <div className="max-w-2xl">
        <h2 className="font-display text-3xl text-cream">Research feed</h2>
        <p className="mt-3 text-sm leading-relaxed text-mute">
          Every few days Cadence searches Europe PMC (free, no account) for recent open-access reviews, trials and guidelines on the reading
          topics and lists them under Reading → New research. Only the search terms are sent: nothing about you, your data or your device.
          Results aren’t reviewed by us, and only the title, journal, a short abstract excerpt and a link are kept.
        </p>
        {!q.data.available && <p className="mt-2 text-xs text-dim">Feed requests are turned off for this server.</p>}
        {READ_ONLY && <p className="mt-2 text-xs text-dim">This setting can only be changed on your Mac.</p>}
      </div>
      <button type="button" role="switch" aria-checked={q.data.enabled} disabled={toggle.isPending || READ_ONLY}
        onClick={() => toggle.mutate(!q.data.enabled)} className={q.data.enabled ? "pop pop-lime" : "pop pop-ghost"}>
        {q.data.enabled ? "On" : "Off"}
      </button>
    </section>
  );
}

function BackupCard() {
  const q = useQuery({ queryKey: ["backup-status"], queryFn: api.backupStatus, refetchInterval: 5 * 60_000 });
  if (q.isPending) return <LoadingBlock height={120} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  const s = q.data;
  const ok = s.configured && !s.stale && !s.last_error;
  const when = s.configured && s.last_success_at ? new Date(`${s.last_success_at}Z`) : null;
  return (
    <section className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 className="font-display text-3xl text-cream">Backups</h2>
          <p className="mt-3 text-sm leading-relaxed text-mute">
            The server copies your database and Garmin archive to Google Drive every night, encrypted before it leaves the server.
            The Garmin key is never backed up.
          </p>
        </div>
        {s.configured && (
          <span className={clsx("chip", ok ? "!border-lime/40 !text-lime" : "!border-amber/50 !text-amber")}>
            {ok ? "Up to date" : s.last_error ? "Last run failed" : "Overdue"}
          </span>
        )}
      </div>
      {!s.configured ? (
        <p className="mt-4 text-sm text-dim">No backup has run on this machine. Nightly backups are set up on the server (see docs/deploy-digitalocean.md).</p>
      ) : (
        <div className="mt-5 space-y-1">
          <p className="num text-3xl text-paper">{when ? timeAgo(when) : "Never succeeded"}</p>
          {when && (
            <p className="text-xs text-dim">
              {when.toLocaleString()}
              {s.snapshot ? ` · snapshot ${s.snapshot}` : ""}
            </p>
          )}
          {s.last_error && <p className="pt-2 text-xs text-coral">{s.last_error}</p>}
          {!s.last_error && s.stale && <p className="pt-2 text-xs text-amber">More than a day and a half since the last successful backup.</p>}
        </div>
      )}
    </section>
  );
}

function BodyProfileCard() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["body-profile"], queryFn: api.bodyProfile });
  const [height, setHeight] = useState("");
  const [birth, setBirth] = useState("");
  const [sex, setSex] = useState<"male" | "female">("male");
  const save = useMutation({
    mutationFn: () => api.setBodyProfile({ height_cm: Number(height), birth_date: birth, sex }),
    onSuccess: () => ["body-profile", "weight"].forEach((k) => client.invalidateQueries({ queryKey: [k] })),
  });
  if (q.isPending) return <LoadingBlock height={160} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  const p = q.data.profile;
  const h = Number(height || p?.height_cm || 0);
  const validHeight = h >= 100 && h <= 250;
  const validBirth = Boolean(birth || p?.birth_date);
  return (
    <section className="surface p-5 sm:p-8">
      <h2 className="font-display text-3xl text-cream">Body profile</h2>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-mute">
        Height, birth date and biological sex — used only by the estimated body-composition formulas on the Weight page (BMI, estimated body
        fat, BMR). Nothing else in Cadence uses this. Stored locally; never sent anywhere.
      </p>
      <form onSubmit={(e) => { e.preventDefault(); if (validHeight && validBirth) save.mutate(); }} className="mt-6 grid gap-5 sm:grid-cols-3">
        <label className="block">
          <span className="eyebrow">Height (cm)</span>
          <input inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder={p ? String(p.height_cm) : "175"}
            className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-2xl text-paper outline-none focus:border-gold" />
        </label>
        <label className="block">
          <span className="eyebrow">Birth date</span>
          <input type="date" value={birth} onChange={(e) => setBirth(e.target.value)} max={new Date().toISOString().slice(0, 10)}
            placeholder={p?.birth_date}
            className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-xl text-paper outline-none focus:border-gold" />
        </label>
        <label className="block">
          <span className="eyebrow">Biological sex</span>
          <p className="mt-1 text-[11px] text-dim">For the formula only</p>
          <Segmented label="Sex" options={[{ value: "male", label: "Male" }, { value: "female", label: "Female" }]} value={sex} onChange={setSex} />
        </label>
        <div className="sm:col-span-3">
          <button type="submit" className="pop pop-lime" disabled={!validHeight || !validBirth || save.isPending}>
            {p ? "Update" : "Save"}
          </button>
          {save.isError && <p className="mt-2 text-xs text-coral">{(save.error as Error).message}</p>}
          {p && <p className="mt-3 text-xs text-dim">Currently: {p.height_cm} cm · born {p.birth_date} · {p.sex}</p>}
        </div>
      </form>
    </section>
  );
}

function CredentialCard() {
  const query = useCredentialStatus();
  if (query.isPending) return <PageSkeleton kind="form" />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const s = query.data;
  const label = LEVEL_LABEL[s.level];

  return (
    <section className="surface h-full p-5 sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-gold/15 text-gold">
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
            <span className="bg-cream px-1.5 py-0.5 text-[11px] font-bold tracking-widest text-ink uppercase">
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
    <section className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-gold/15 text-gold">
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

/** Lets the Claude app (including on the iPhone) read your data, read-only, through a connector you approve here. */
function ClaudeConnectorCard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["connector"], queryFn: api.connector, refetchInterval: 30_000 });
  const onSuccess = (v: ConnectorStatus) => client.setQueryData(["connector"], v);
  const toggle = useMutation({ mutationFn: api.connectorSet, onSuccess });
  const newCode = useMutation({ mutationFn: api.connectorCode, onSuccess });
  const writes = useMutation({ mutationFn: api.connectorWrites, onSuccess });
  const revoke = useMutation({ mutationFn: api.connectorRevoke, onSuccess });
  const [revoking, setRevoking] = useState<{ id: string; label: string } | null>(null);
  const [copied, setCopied] = useState(false);
  if (query.isPending) return <LoadingBlock height={200} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const c = query.data;
  const error = toggle.error ?? newCode.error ?? revoke.error ?? writes.error;
  const copy = async () => {
    if (!c.address) return;
    try {
      await navigator.clipboard.writeText(c.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the address is shown below to copy by hand */
    }
  };
  return (
    <section className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-gold/15 text-gold">
            <Sparkles size={18} />
          </div>
          <div>
            <h2 className="font-semibold text-paper">Claude</h2>
            <p className="text-xs text-mute">Ask Claude about your data · no API key</p>
          </div>
        </div>
        <button type="button" className={c.enabled ? "pop pop-ghost" : "pop pop-lime"} disabled={toggle.isPending} onClick={() => toggle.mutate(!c.enabled)}>
          {c.enabled ? "Turn off" : "Turn on"}
        </button>
      </div>
      <p className="mt-4 max-w-2xl text-sm text-mute">
        Adds Cadence to the Claude app as a connector. Once it’s set up on claude.ai, it works in the Claude app on your iPhone too, on your normal Claude
        account. Claude can look at your training, sleep, weight, food and plan. By default it can’t change anything. What it reads becomes part of that conversation
        with Claude, so it leaves this server when you ask a question.
      </p>
      {c.enabled && !c.address && (
        <p role="note" className="mt-4 border-l-2 border-gold/60 pl-3 text-xs text-mute">
          Claude reaches Cadence from the internet, so this needs the server’s secure address (CADENCE_PUBLIC_URL, see the deploy guide). On this Mac
          alone there is nothing for Claude to connect to.
        </p>
      )}
      {c.enabled && c.address && !c.running && (
        <p role="note" className="mt-4 border-l-2 border-gold/60 pl-3 text-xs text-mute">Phone sharing is switched off, which also stops the connector. Turn it on in the phone card below.</p>
      )}
      {c.enabled && c.address && c.running && (
        <ol className="mt-6 space-y-4 text-sm text-mute">
          <li>
            <span className="num mr-2 text-gold">1</span>On claude.ai (web or desktop), open <span className="text-paper">Settings → Connectors → Add custom connector</span> and
            paste this address:
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <code className="num rounded-lg bg-white/5 px-3 py-2 text-xs break-all text-paper">{c.address}</code>
              <button type="button" className="pop pop-ghost !px-3 !py-1.5 text-xs" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
            </div>
          </li>
          <li>
            <span className="num mr-2 text-gold">2</span>Claude opens a Cadence page. Type this approval code there:
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <span className="num rounded-lg bg-white/5 px-4 py-2 text-2xl tracking-[0.25em] text-cream">{c.code ?? "…"}</span>
              <span className="text-xs text-dim">
                {c.code_expires_in_s != null ? `Works once, expires in ${Math.max(1, Math.round(c.code_expires_in_s / 60))} min.` : ""}
              </span>
              <button type="button" className="pop pop-ghost !px-3 !py-1.5 text-xs" disabled={newCode.isPending} onClick={() => newCode.mutate()}>New code</button>
            </div>
          </li>
          <li><span className="num mr-2 text-gold">3</span>Open the Claude app on your iPhone, start a chat, and switch Cadence on under the tools menu.</li>
        </ol>
      )}
      {c.enabled && (
        <div className="mt-8 border-t border-line pt-4">
          <div className="space-y-5">
            {([
              { group: "log", on: c.writes, title: "Let Claude log things",
                text: "Off: Claude only reads. On: it can also log food and saved meals, remove a food entry (restorable for a week), record your weight and save a check-in, when you ask it to." },
              { group: "plan", on: c.plan_writes, title: "Let Claude change plan and goals",
                text: "Off by default, separate from the above. On: it can set or clear your race goal, add, change or drop goals, add or remove planned sessions (removing one also takes it off your watch if it was sent) and add or remove time off. It can't change plan settings, Garmin, credentials or sharing." },
            ] as const).map((w) => (
              <div key={w.group} className="flex flex-wrap items-center justify-between gap-3">
                <div className="max-w-xl">
                  <h3 className="eyebrow mb-1">{w.title}</h3>
                  <p className="text-sm text-mute">{w.text}</p>
                </div>
                <button type="button" role="switch" aria-checked={w.on} aria-label={w.title} className={w.on ? "pop pop-lime" : "pop pop-ghost"}
                  disabled={writes.isPending} onClick={() => writes.mutate({ group: w.group, enabled: !w.on })}>
                  {w.on ? "On" : "Off"}
                </button>
              </div>
            ))}
          </div>
          {c.recent.length > 0 && (
            <ul className="mt-4 space-y-1 text-xs text-dim">
              {c.recent.slice(0, 6).map((r, i) => (
                <li key={`${r.at}-${i}`}>
                  <span className="num text-mute">{timeAgo(new Date(`${r.at}Z`))}</span> · {r.summary}{r.ok ? "" : " (didn’t go through)"}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {c.enabled && (
        <div className="mt-8 border-t border-line pt-4">
          <h3 className="eyebrow mb-3">Connected</h3>
          {c.connections.length === 0 ? (
            <p className="text-sm text-mute">Nothing connected yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {c.connections.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm text-paper">{p.label || "Claude"}</p>
                    <p className="text-xs text-dim">
                      Connected {new Date(`${p.created_at}Z`).toLocaleDateString()} ·{" "}
                      {p.last_used_at ? `last used ${timeAgo(new Date(`${p.last_used_at}Z`))}` : "not used yet"}
                    </p>
                  </div>
                  <button type="button" className="pop pop-ghost !px-3 !py-1.5 text-xs" disabled={revoke.isPending} onClick={() => setRevoking({ id: p.id, label: p.label || "this connection" })}>
                    Disconnect
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <ConfirmDialog
        open={revoking != null}
        title="Disconnect Claude?"
        body={`${revoking?.label ?? "This connection"} will stop working at once and will need a new approval code to connect again.`}
        confirmLabel="Disconnect"
        onCancel={() => setRevoking(null)}
        onConfirm={() => {
          if (revoking) revoke.mutate(revoking.id);
          setRevoking(null);
        }}
      />
      {error && <p className="mt-4 text-sm text-coral">{error.message}</p>}
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
  const revoke = useMutation({ mutationFn: api.shareRevoke, onSuccess });
  const [revoking, setRevoking] = useState<{ id: string; label: string } | null>(null);
  // Each QR code lives for pair_expires_in_s; count down locally and ask the server for a fresh one at zero.
  const expiresIn = query.data?.pair_expires_in_s ?? null;
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    if (expiresIn == null) return setLeft(null);
    const end = Date.now() + expiresIn * 1000;
    setLeft(expiresIn);
    const t = setInterval(() => {
      const r = Math.max(0, Math.ceil((end - Date.now()) / 1000));
      setLeft(r);
      if (r === 0) {
        clearInterval(t);
        query.refetch();
      }
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expiresIn, query.dataUpdatedAt]);
  if (query.isPending) return <LoadingBlock height={220} />;
  if (query.isError || !Array.isArray(query.data?.sessions)) return <ErrorBlock error={query.error ?? new Error("Unexpected response from the sharing service")} retry={() => query.refetch()} />;
  const s = query.data;
  const error = start.error ?? stop.error ?? reset.error ?? revoke.error;

  return (
    <section className="surface p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-violet/15 text-violet">
            <Smartphone size={18} />
          </div>
          <div>
            <h2 className="font-semibold text-paper">On your iPhone</h2>
            <p className="text-xs text-mute">Read-only · paired by QR code</p>
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
                {s.secure ? "Make sure your iPhone has internet." : "Join the same Wi-Fi as this Mac."}
              </li>
              <li><span className="num mr-2 text-gold">2</span>Point the Camera at the code and open the link.</li>
              <li><span className="num mr-2 text-gold">3</span>In Safari tap Share → <span className="text-paper">Add to Home Screen</span>, open Cadence from there, and turn on notifications in Settings.</li>
            </ol>
            {s.insecure_lan && (
              <p role="note" className="mt-6 border-l-2 border-gold/60 bg-gold/5 p-3 text-xs text-mute">
                <span className="text-paper">Home Wi-Fi only, over plain HTTP.</span> Anyone on this network could see the traffic, so only
                pair on a network you trust. Offline mode and notifications on the iPhone need a secure https:// address (see the server setup docs).
              </p>
            )}
            <p className="mt-4 text-xs text-dim">
              Each code works once, for one phone.{" "}
              {left != null && (left > 0
                ? <>This one expires in <span className="num text-mute">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span>.</>
                : "This one has expired; getting a new one…")}
            </p>
            {!s.secure && (
              <p className="mt-6 border-l-2 border-gold/60 pl-3 text-xs text-mute">
                For access away from home and for notifications you need an https:// address: run Cadence on the server and set{" "}
                <span className="num text-paper">CADENCE_PUBLIC_URL</span> (docs/deploy-digitalocean.md). This page will switch to it
                automatically.
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
            <p className="mt-3 text-xs text-dim">“New pairing code” issues a fresh code; to unpair a phone, revoke it below.</p>
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
      <div className="mt-8 border-t border-line pt-4">
        <h3 className="eyebrow mb-3">Paired phones</h3>
        {s.sessions.length === 0 ? (
          <p className="text-sm text-mute">No phones are paired yet.</p>
        ) : (
          <ul className="divide-y divide-line">
            {s.sessions.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm text-paper">{p.label || "Phone"}</p>
                  <p className="text-xs text-dim">
                    Paired {new Date(`${p.created_at}Z`).toLocaleDateString()} ·{" "}
                    {p.last_seen_at ? `last seen ${timeAgo(new Date(`${p.last_seen_at}Z`))}` : "not seen yet"}
                  </p>
                </div>
                <button type="button" className="pop pop-ghost !px-3 !py-1.5 text-xs" disabled={revoke.isPending}
                  onClick={() => setRevoking({ id: p.id, label: p.label || "this phone" })}>
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={revoking != null}
        title="Revoke this phone?"
        body={`${revoking?.label ?? "This phone"} will be signed out and will need a new pairing code to open Cadence again.`}
        confirmLabel="Revoke"
        onCancel={() => setRevoking(null)}
        onConfirm={() => {
          if (revoking) revoke.mutate(revoking.id);
          setRevoking(null);
        }}
      />
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
      <path d={path} fill={C.ink} />
    </svg>
  );
}

function PrivacyCard() {
  return (
    <section className="surface h-full p-5 sm:p-8">
      <div className="grid h-11 w-11 place-items-center rounded-2xl bg-lime/10 text-lime">
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

const SOURCE_ICON = { demo: Database, garmin: Watch } as const;
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
    <section className="surface p-5 sm:p-8">
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
        <div className="overflow-x-auto">
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
        </div>
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
      <div className="grid h-11 w-11 place-items-center rounded-2xl border border-line-strong text-cream">
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
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="surface dialog-content dialog-center">
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
