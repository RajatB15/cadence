import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Bookmark, BookmarkCheck, Check, ExternalLink, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { EVIDENCE, readTime, sourceLine } from "../lib/reading";
import type { ReadingCard, ReadingView } from "../lib/types";
import { Sheet } from "./Sheet";

export function useReading() {
  return useQuery({ queryKey: ["reading"], queryFn: api.reading, staleTime: 60_000 });
}

export function useSetReading() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "read" | "saved" | "skipped" | "unread" }) => api.setReading(id, status),
    onSuccess: (view: ReadingView) => client.setQueryData(["reading"], view),
  });
}

const topicLabel = (view: ReadingView | undefined, key: string) => view?.topics.find((t) => t.key === key)?.label ?? key;

/** The whole card: summary, takeaways, how strong the evidence is, limits, and the source link. */
export function ReadingBody({ card, why }: { card: ReadingCard; why?: string }) {
  const set = useSetReading();
  const evidence = EVIDENCE[card.evidence];
  const saved = card.status === "saved";
  return (
    <div className="space-y-6">
      {why && <p className="text-sm text-mute">{why}</p>}
      <p className="text-lg leading-relaxed text-paper">{card.summary}</p>
      {card.takeaways.length > 0 && (
        <ul className="space-y-2 border-l border-gold/40 pl-4 text-paper">
          {card.takeaways.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      <div className="space-y-2 text-sm">
        <p>
          <span className="chip mr-2">{evidence.label}</span>
          <span className="text-mute">{evidence.note}</span>
        </p>
        {card.caution && <p className="text-mute">Keep in mind: {card.caution}</p>}
      </div>
      <p className="text-xs text-dim">
        {sourceLine(card)} · {card.source.licence}. Summarised in our own words; read the original for the full picture.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <a href={card.source.url} target="_blank" rel="noopener noreferrer" className="pop">
          Open source <ExternalLink size={14} />
        </a>
        <button type="button" className="pop pop-ghost" disabled={set.isPending} onClick={() => set.mutate({ id: card.id, status: card.status === "read" ? "unread" : "read" })}>
          <Check size={14} /> {card.status === "read" ? "Read · undo" : "Mark as read"}
        </button>
        <button type="button" className="pop pop-ghost" disabled={set.isPending} onClick={() => set.mutate({ id: card.id, status: saved ? "unread" : "saved" })}>
          {saved ? <BookmarkCheck size={14} /> : <Bookmark size={14} />} {saved ? "Saved" : "Save for later"}
        </button>
      </div>
      {set.isError && (
        <p role="alert" className="text-sm text-coral">
          Couldn’t save that. Try again.
        </p>
      )}
    </div>
  );
}

export function ReadingSheet({ card, view, why, onClose }: { card: ReadingCard | null; view?: ReadingView; why?: string; onClose: () => void }) {
  return (
    <Sheet open={card != null} onOpenChange={(o) => !o && onClose()} eyebrow={card ? `${topicLabel(view, card.topic)} · ${readTime(card)}` : ""} title={card?.title ?? ""}>
      {card && <ReadingBody card={card} why={why} />}
    </Sheet>
  );
}

/** Home card: one cited read for today. Hidden until a library exists, so it never shows an empty shell. */
export function TodayReadCard() {
  const query = useReading();
  const set = useSetReading();
  const [open, setOpen] = useState(false);
  if (query.isPending) return <div className="surface h-40 animate-pulse" aria-busy="true" aria-label="Loading today’s read" />;
  if (query.isError) return null;
  const view = query.data;
  if (!view.available) return null;
  const card = view.today;
  if (!card) {
    return (
      <div className="surface p-6 text-mute">
        <p className="eyebrow mb-2 flex items-center gap-2"><BookOpen size={12} /> Today’s read</p>
        Nothing left unread. <Link to="/reading" className="text-gold underline">Browse the library</Link>.
      </div>
    );
  }
  return (
    <>
      <div className="surface space-y-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="eyebrow flex items-center gap-2">
            <BookOpen size={12} /> Today’s read · {topicLabel(view, card.topic)} · {readTime(card)}
          </p>
          <Link to="/reading" className="text-xs tracking-widest text-dim uppercase hover:text-paper">Library</Link>
        </div>
        <h2 className="font-display text-3xl leading-tight text-cream">{card.title}</h2>
        <p className="line-clamp-3 text-mute">{card.summary}</p>
        <p className="text-xs text-dim">{card.why}</p>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="pop" onClick={() => setOpen(true)}>
            Read
          </button>
          <button type="button" className="pop pop-ghost" disabled={set.isPending} onClick={() => set.mutate({ id: card.id, status: "skipped" })}>
            <RefreshCw size={14} /> Another
          </button>
        </div>
        {set.isError && <p role="alert" className="text-sm text-coral">Couldn’t change the pick. Try again.</p>}
      </div>
      <ReadingSheet card={open ? card : null} view={view} why={card.why} onClose={() => setOpen(false)} />
    </>
  );
}
