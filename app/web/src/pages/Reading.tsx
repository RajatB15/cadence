import { clsx } from "clsx";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bookmark, Check, ExternalLink, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ReadingSheet, useReading, useSetReading } from "../components/Reading";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { EVIDENCE, checkedAgo, filterCards, filterFeed, readTime, type ReadingFilter } from "../lib/reading";
import type { ReadingView } from "../lib/types";

const FILTERS: { key: ReadingFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "saved", label: "Saved" },
  { key: "read", label: "Read" },
];

export function ReadingPage() {
  const query = useReading();
  const [topic, setTopic] = useState<string | null>(null);
  const [filter, setFilter] = useState<ReadingFilter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [tab, setTab] = useState<"library" | "research">("library");
  const view = query.data;
  const cards = view ? filterCards(view.cards, topic, filter) : [];
  const open = view?.cards.find((c) => c.id === openId) ?? null;
  return (
    <>
      <PageHeader eyebrow={view?.available ? `${view.cards.length} cards · ${view.counts.read} read` : "Reading"} title={<>Worth <em className="text-gold">reading.</em></>} />
      {query.isPending ? (
        <LoadingBlock height={240} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : !view?.available ? (
        <div className="surface p-12 text-center text-mute">
          No reading library found. Put card files in <code>reading-data/cards/</code> (see its README) and reload.
        </div>
      ) : (
        <>
          <div className="mb-6 flex gap-2" role="tablist" aria-label="Reading">
            <Chip active={tab === "library"} onClick={() => setTab("library")}>Library</Chip>
            <Chip active={tab === "research"} onClick={() => setTab("research")}>
              New research{view.feed.items.length > 0 ? ` · ${view.feed.items.length}` : ""}
            </Chip>
          </div>
          <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Topic">
            <Chip active={topic == null} onClick={() => setTopic(null)}>All topics</Chip>
            {view.topics.filter((t) => t.count > 0).map((t) => (
              <Chip key={t.key} active={topic === t.key} onClick={() => setTopic(t.key)}>{t.label} · {t.count}</Chip>
            ))}
          </div>
          {tab === "library" && (
            <div className="mb-8 flex flex-wrap gap-2" role="group" aria-label="Show">
              {FILTERS.map((f) => (
                <Chip key={f.key} active={filter === f.key} onClick={() => setFilter(f.key)}>{f.label}</Chip>
              ))}
            </div>
          )}
          {view.skipped_invalid > 0 && (
            <p className="mb-4 text-sm text-mute">{view.skipped_invalid} card{view.skipped_invalid === 1 ? " was" : "s were"} skipped because they were incomplete or duplicated.</p>
          )}
          {tab === "research" ? (
            <ResearchFeed view={view} topic={topic} />
          ) : cards.length === 0 ? (
            <div className="surface p-12 text-center text-mute">Nothing matches. Try another topic or filter.</div>
          ) : (
            <ul className="grid gap-4 md:grid-cols-2">
              {cards.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => setOpenId(c.id)} className="surface surface-hover block h-full w-full space-y-3 p-5 text-left">
                    <p className="eyebrow flex items-center justify-between gap-2">
                      <span>{view.topics.find((t) => t.key === c.topic)?.label} · {readTime(c)}</span>
                      <span className="flex items-center gap-2 text-gold">
                        {c.status === "saved" && <Bookmark size={12} aria-label="Saved" />}
                        {c.status === "read" && <Check size={12} aria-label="Read" />}
                        {c.status === "skipped" && <span className="text-dim">Skipped</span>}
                      </span>
                    </p>
                    <h2 className="font-display text-2xl leading-tight text-cream">{c.title}</h2>
                    <p className="line-clamp-3 text-sm text-mute">{c.summary}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <ReadingSheet card={open} view={view} onClose={() => setOpenId(null)} />
        </>
      )}
    </>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={clsx("chip pointer-coarse:py-2", active ? "border-gold text-cream" : "text-mute hover:text-paper")}>
      {children}
    </button>
  );
}

function ResearchFeed({ view, topic }: { view: ReadingView; topic: string | null }) {
  const client = useQueryClient();
  const set = useSetReading();
  const [savedOnly, setSavedOnly] = useState(false);
  const refresh = useMutation({
    mutationFn: api.refreshReadingFeed,
    // The fetch runs in the background; look again shortly for what it stored.
    onSuccess: () => setTimeout(() => client.invalidateQueries({ queryKey: ["reading"] }), 8000),
  });
  const { feed } = view;
  const items = filterFeed(feed.items, topic, savedOnly);
  const topicLabel = (key: string) => view.topics.find((t) => t.key === key)?.label ?? key;
  if (!feed.available) {
    return <div className="surface p-12 text-center text-mute">The research feed is turned off for this server.</div>;
  }
  if (!feed.enabled) {
    return (
      <div className="surface p-12 text-center text-mute">
        The research feed is switched off. Turn it on in <Link to="/settings" className="text-gold underline">Settings</Link>.
      </div>
    );
  }
  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-mute">
          Recent open-access reviews, trials and guidelines from Europe PMC, found by topic search. We haven’t read or vetted them: the label shows the type of
          paper, not how good it is. You see the first lines of the abstract and a link to the paper.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Chip active={savedOnly} onClick={() => setSavedOnly((v) => !v)}>Saved only</Chip>
          <button type="button" className="pop pop-ghost" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            <RefreshCw size={14} /> {refresh.isPending ? "Checking…" : "Check now"}
          </button>
        </div>
      </div>
      {(refresh.data?.reason || checkedAgo(feed.fetched_at)) && <p className="mb-4 text-xs text-dim">{refresh.data?.reason ?? checkedAgo(feed.fetched_at)}</p>}
      {refresh.isError && <p role="alert" className="mb-4 text-sm text-coral">Couldn’t start a check. Try again.</p>}
      {items.length === 0 ? (
        <div className="surface p-12 text-center text-mute">
          {feed.fetched_at ? "Nothing here for this filter." : "Nothing fetched yet. The first check runs in the background; press Check now if it doesn’t appear in a minute."}
        </div>
      ) : (
        <ul className="space-y-4">
          {items.map((i) => (
            <li key={i.id} className="surface space-y-3 p-5">
              <p className="eyebrow flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>{topicLabel(i.topic)}</span>
                <span className="chip">{EVIDENCE[i.evidence].label}</span>
                <span className="text-dim">{formatDate(i.published)}{i.journal ? ` · ${i.journal}` : ""}</span>
              </p>
              <h2 className="font-display text-2xl leading-tight text-cream">{i.title}</h2>
              <p className="text-sm text-mute">{i.snippet}</p>
              <div className="flex flex-wrap items-center gap-3">
                <a href={i.url} target="_blank" rel="noopener noreferrer" className="pop">Open paper <ExternalLink size={14} /></a>
                <button type="button" className="pop pop-ghost" disabled={set.isPending} onClick={() => set.mutate({ id: i.id, status: i.status === "saved" ? "unread" : "saved" })}>
                  <Bookmark size={14} /> {i.status === "saved" ? "Saved" : "Save"}
                </button>
                <button type="button" className="pop pop-ghost" disabled={set.isPending} onClick={() => set.mutate({ id: i.id, status: "skipped" })}>
                  <X size={14} /> Dismiss
                </button>
                <span className="text-xs text-dim">{i.licence}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
