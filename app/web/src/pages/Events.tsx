import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Link2Off } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ShareEventButton } from "../components/EventShare";
import { MoreMenu } from "../components/MoreMenu";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { dayLabel, eventDates, eventStats } from "../lib/events";
import { formatDate, formatDuration, formatKm } from "../lib/format";
import { ACTIVITY_FAMILIES, activityStyle } from "../lib/metrics";
import type { EventDay, EventDetail, EventSummary } from "../lib/types";

function Stats({ stats }: { stats: { label: string; value: string }[] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 lg:grid-cols-7">
      {stats.map((s) => (
        <div key={s.label}>
          <dd className="num text-2xl text-paper sm:text-3xl">{s.value}</dd>
          <dt className="text-[10px] tracking-widest text-dim uppercase">{s.label}</dt>
        </div>
      ))}
    </dl>
  );
}

function Families({ families }: { families: Record<string, number> }) {
  return (
    <span className="flex flex-wrap gap-2">
      {Object.entries(families).map(([f, n]) => (
        <span key={f} className="chip" style={{ borderColor: `${ACTIVITY_FAMILIES[f]?.color ?? "#888"}66`, color: ACTIVITY_FAMILIES[f]?.color }}>
          {ACTIVITY_FAMILIES[f]?.label ?? f} · {n}
        </span>
      ))}
    </span>
  );
}

export function EventsPage() {
  const query = useQuery({ queryKey: ["events"], queryFn: api.events });
  const items = query.data?.items ?? [];
  return (
    <>
      <PageHeader eyebrow={query.data ? `${items.length} on record` : "Events"} title={<>Treks &amp; <em className="text-gold">multisport.</em></>}>
        <Link to="/activities" className="pop pop-ghost">Back to activities</Link>
      </PageHeader>
      {query.isPending ? (
        <LoadingBlock height={240} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <div className="surface p-12 text-center text-mute">
          No events yet. On Activities choose “Group into event”, pick the days or legs, and name it.
        </div>
      ) : (
        <ul className="space-y-4">
          {items.map((e) => (
            <EventCard key={e.id} e={e} />
          ))}
        </ul>
      )}
    </>
  );
}

function EventCard({ e }: { e: EventSummary }) {
  return (
    <li>
      <Link to={`/events/${e.id}`} className="surface surface-hover block space-y-5 p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="font-display text-3xl text-cream">{e.name}</h2>
          <p className="text-sm text-mute">
            {eventDates(e.start, e.end)}
            {e.span_days > 1 && ` · ${e.span_days} days`} · {e.totals.count} activit{e.totals.count === 1 ? "y" : "ies"}
          </p>
        </div>
        <Families families={e.families} />
        {e.totals.count > 0 && <Stats stats={eventStats(e.totals)} />}
        {e.missing > 0 && <Missing n={e.missing} />}
      </Link>
    </li>
  );
}

function Missing({ n }: { n: number }) {
  return (
    <p className="text-xs text-gold">
      {n} linked activit{n === 1 ? "y isn't" : "ies aren't"} in the vault right now (run a sync); the link is kept and totals exclude {n === 1 ? "it" : "them"}.
    </p>
  );
}

export function EventPage() {
  const id = Number(useParams().id);
  const query = useQuery({ queryKey: ["event", id], queryFn: () => api.event(id), enabled: Number.isFinite(id) });
  if (query.isPending) return <LoadingBlock height={640} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  return <Detail e={query.data} />;
}

function Detail({ e }: { e: EventDetail }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(e.name);
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["event"] });
    client.invalidateQueries({ queryKey: ["events"] });
    client.invalidateQueries({ queryKey: ["activities"] });
    client.invalidateQueries({ queryKey: ["activity"] });
  };
  const rename = useMutation({ mutationFn: () => api.renameEvent(e.id, name), onSuccess: () => { setRenaming(false); refresh(); } });
  const unlink = useMutation({
    mutationFn: (activityId: number) => api.unlinkFromEvent(e.id, activityId),
    onSuccess: (r) => { refresh(); if (!r.event) navigate("/events"); },
  });
  const dissolve = useMutation({ mutationFn: () => api.deleteEvent(e.id), onSuccess: () => { refresh(); navigate("/events"); } });
  const error = rename.error ?? unlink.error ?? dissolve.error;

  return (
    <div className="space-y-10">
      <Link to="/events" className="eyebrow inline-flex items-center gap-2 hover:text-paper">
        <ArrowLeft size={12} /> All events
      </Link>
      <header className="space-y-4">
        <div className="eyebrow flex flex-wrap items-center gap-3">
          <span>
            {eventDates(e.start, e.end)}
            {e.span_days > 1 && ` · ${e.span_days} days`}
          </span>
          <span className="ml-auto flex items-center gap-2">
            {e.totals.count > 0 && <ShareEventButton event={e} />}
            {!READ_ONLY && (
              <MoreMenu
                items={[
                  { label: "Rename event", onSelect: () => setRenaming(true) },
                  {
                    label: "Dissolve event",
                    hint: "The activities stay; only the grouping is removed.",
                    onSelect: () => { if (window.confirm("Dissolve this event? The activities stay; only the grouping is removed.")) dissolve.mutate(); },
                  },
                ]}
              />
            )}
          </span>
        </div>
        {renaming ? (
          <form onSubmit={(ev) => { ev.preventDefault(); rename.mutate(); }} className="flex flex-wrap gap-3">
            <input aria-label="Event name" className="min-w-0 flex-1 border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold text-2xl" maxLength={120} value={name} onChange={(ev) => setName(ev.target.value)} autoFocus />
            <button type="submit" className="pop pop-lime" disabled={!name.trim() || rename.isPending}>Save</button>
            <button type="button" className="pop pop-ghost" onClick={() => { setRenaming(false); setName(e.name); }}>Cancel</button>
          </form>
        ) : (
          <h1 className="font-display text-5xl leading-[0.95] text-cream sm:text-7xl">{e.name}</h1>
        )}
        <Families families={e.families} />
      </header>

      {error && <ErrorBlock error={error} />}
      {e.missing > 0 && <Missing n={e.missing} />}
      {e.totals.count > 0 ? (
        <>
          <section aria-label="Totals" className="surface p-6">
            <Stats stats={eventStats(e.totals)} />
            <p className="mt-4 text-xs text-dim">
              Moving time is the sum of the recordings; elapsed runs from the first start to the last finish, so it includes nights and breaks. Figures a recording
              doesn’t carry show “—” and are left out of the sums. Each activity still counts on its own day in your load and fitness; grouping adds nothing.
            </p>
          </section>
          <section aria-label="Days" className="space-y-4">
            {e.days.map((d) => (
              <DayCard key={d.day} d={d} onUnlink={READ_ONLY ? undefined : (id) => unlink.mutate(id)} busy={unlink.isPending} />
            ))}
          </section>
        </>
      ) : (
        <div className="surface p-12 text-center text-mute">None of this event’s activities are in the vault right now.</div>
      )}

    </div>
  );
}

function DayCard({ d, onUnlink, busy }: { d: EventDay; onUnlink?: (activityId: number) => void; busy: boolean }) {
  const r = d.recovery;
  return (
    <article className="surface space-y-4 p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-3xl text-cream">
          {dayLabel(d.number)} <span className="text-base text-mute">{formatDate(d.day)}</span>
        </h2>
        <p className="num text-sm text-mute">
          {formatKm(d.totals.distance_m ?? null)} km · {formatDuration(d.totals.moving_s ?? 0)}
          {d.totals.elevation_gain_m != null && ` · ↑${Math.round(d.totals.elevation_gain_m)} m`}
        </p>
      </div>
      <ul className="divide-y divide-line">
        {d.activities.map((a) => {
          const style = activityStyle(a.type, a.family);
          return (
            <li key={a.id} className="flex items-center gap-4 py-3">
              <style.icon size={16} style={{ color: style.color }} className="shrink-0" aria-hidden />
              <Link to={`/activities/${a.id}`} className="min-w-0 flex-1 truncate font-semibold text-paper hover:underline">{a.name}</Link>
              <span className="num shrink-0 text-sm text-mute">
                {a.distance_m != null && `${formatKm(a.distance_m)} km · `}{formatDuration(a.duration_s)}
              </span>
              {onUnlink && (
                <button type="button" aria-label={`Unlink ${a.name}`} title="Unlink from this event" disabled={busy} className="shrink-0 text-dim hover:text-coral" onClick={() => onUnlink(a.id)}>
                  <Link2Off size={16} />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-dim">
        {r
          ? `Recovery that morning: ${[r.sleep_h != null && `sleep ${r.sleep_h.toFixed(1)} h`, r.hrv_ms != null && `HRV ${Math.round(r.hrv_ms)} ms`, r.rhr != null && `resting ${Math.round(r.rhr)} bpm`].filter(Boolean).join(" · ")}`
          : "No sleep or HRV recorded for this day."}
      </p>
    </article>
  );
}
