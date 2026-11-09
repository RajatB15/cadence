import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Check, ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { leftNote, percentRead, spanMinutes } from "../lib/book";
import type { BookPart, BookView } from "../lib/types";
import { ErrorBlock, LoadingBlock } from "./Shell";
import { Sheet } from "./Sheet";

export function useBook() {
  return useQuery({ queryKey: ["reading-book"], queryFn: api.readingBook, staleTime: 60_000 });
}

function useBookMoves() {
  const client = useQueryClient();
  const onSuccess = (view: BookView) => client.setQueryData(["reading-book"], view);
  return {
    read: useMutation({ mutationFn: api.readBookPart, onSuccess }),
    jump: useMutation({ mutationFn: api.setBookPosition, onSuccess }),
  };
}

/** The text of one part, as written: headings, paragraphs and lists. */
function PartText({ part }: { part: BookPart }) {
  return (
    <div className="max-w-[68ch] space-y-4 text-[17px] leading-relaxed text-paper">
      {part.blocks.map(([kind, text], i) =>
        kind === "h" ? (
          <h3 key={i} className="pt-3 font-display text-2xl leading-tight text-cream">{text}</h3>
        ) : kind === "li" ? (
          <p key={i} className="border-l border-gold/40 pl-4 text-mute">{text}</p>
        ) : (
          <p key={i}>{text}</p>
        ),
      )}
    </div>
  );
}

function Attribution({ view }: { view: BookView }) {
  const b = view.book!;
  return (
    <p className="text-xs text-dim">
      <a href={b.url} target="_blank" rel="noopener noreferrer" className="underline">{b.title}</a> · {b.authors} · licensed{" "}
      <a href={b.licence_url} target="_blank" rel="noopener noreferrer" className="underline">{b.licence}</a>. {b.note}
    </p>
  );
}

/** The reader: today's part, a clear "done" step that moves you on, and the chapters to jump between. */
export function BookPanel() {
  const query = useBook();
  const { read, jump } = useBookMoves();
  const [chapters, setChapters] = useState(false);
  if (query.isPending) return <LoadingBlock height={320} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const view = query.data;
  if (!view.available || !view.progress || !view.chapters) {
    return <div className="surface p-12 text-center text-mute">No book found. Put one in <code>reading-data/books/</code> and reload.</div>;
  }
  const part = view.current;
  const pr = view.progress;
  return (
    <div className="space-y-6">
      <div className="surface space-y-4 p-6 sm:p-8">
        <p className="eyebrow flex flex-wrap items-center gap-x-3">
          <span>{view.book!.title}</span>
          <span className="text-dim">{percentRead(pr)}% read · {view.days_read ?? 0} day{view.days_read === 1 ? "" : "s"} reading</span>
        </p>
        <div className="h-1 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={percentRead(pr)} aria-valuemin={0} aria-valuemax={100} aria-label="Book progress">
          <div className="h-full rounded-full bg-gold transition-[width] duration-500" style={{ width: `${percentRead(pr)}%` }} />
        </div>
        <p className="text-sm text-mute">{leftNote(pr)}</p>
      </div>
      {part ? (
        <article className="surface space-y-6 p-6 sm:p-10">
          <header className="space-y-1">
            <p className="eyebrow">{part.chapter_title} · part {part.n} of {part.of} · {part.read_min} min</p>
            {view.read_today && <p className="text-sm text-lime">You’ve read today. This one’s extra, if you feel like it.</p>}
          </header>
          <PartText part={part} />
          <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
            <button type="button" className="pop" disabled={read.isPending} onClick={() => read.mutate(undefined, { onSuccess: () => window.scrollTo({ top: 0, behavior: "smooth" }) })}>
              <Check size={14} /> {read.isPending ? "Saving…" : "Done, mark as read"}
            </button>
            <span className="text-xs text-dim">Your place is kept; stopping mid-way costs nothing.</span>
          </div>
          {read.isError && <p role="alert" className="text-sm text-coral">Couldn’t save your place. Try again.</p>}
        </article>
      ) : (
        <div className="surface p-10 text-center text-mute">That’s the whole book. Pick a chapter below to read any of it again.</div>
      )}
      <div className="surface p-6">
        <button type="button" className="flex w-full items-center justify-between text-left" aria-expanded={chapters} onClick={() => setChapters((v) => !v)}>
          <span className="eyebrow">Chapters · {view.chapters.length}</span>
          <ChevronDown size={16} className={chapters ? "rotate-180 transition" : "transition"} />
        </button>
        {chapters && (
          <ul className="mt-4 divide-y divide-line">
            {view.chapters.map((c) => (
              <li key={c.first} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-paper">{c.title}</p>
                  <p className="text-xs text-dim">{c.done >= c.parts ? "Read" : `${c.done} of ${c.parts} parts`}</p>
                </div>
                <button type="button" className="pop pop-ghost" disabled={jump.isPending} onClick={() => jump.mutate(c.first + (c.done >= c.parts ? 0 : c.done), { onSuccess: () => window.scrollTo({ top: 0, behavior: "smooth" }) })}>
                  {c.done >= c.parts ? "Read again" : c.done > 0 ? "Continue here" : "Start here"}
                </button>
              </li>
            ))}
          </ul>
        )}
        {jump.isError && <p role="alert" className="mt-3 text-sm text-coral">Couldn’t move your place. Try again.</p>}
      </div>
      <Attribution view={view} />
    </div>
  );
}

/** Home: today's few minutes of the book. Hidden until a book exists. */
export function TodayBookCard() {
  const query = useBook();
  const { read } = useBookMoves();
  const [open, setOpen] = useState(false);
  if (query.isPending) return <div className="surface h-32 animate-pulse" aria-busy="true" aria-label="Loading your book" />;
  if (query.isError) return <div className="surface p-6 text-sm text-mute">Your book couldn’t load. <button type="button" className="text-gold underline" onClick={() => query.refetch()}>Retry</button></div>;
  const view = query.data;
  if (!view.available || !view.progress) return null;
  const part = view.current;
  return (
    <>
      <div className="surface space-y-3 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="eyebrow flex items-center gap-2"><BookOpen size={12} /> Your book · {percentRead(view.progress)}% read</p>
          <Link to="/reading" className="text-xs tracking-widest text-dim uppercase hover:text-paper">Chapters</Link>
        </div>
        {part ? (
          <>
            <h2 className="font-display text-2xl leading-tight text-cream sm:text-3xl">{part.chapter_title}</h2>
            <p className="text-sm text-mute">Part {part.n} of {part.of} · {spanMinutes(part.read_min)}{view.read_today ? " · you’ve read today" : ""}</p>
            <button type="button" className="pop" onClick={() => setOpen(true)}>{view.read_today ? "Read more" : "Read today’s part"}</button>
          </>
        ) : (
          <p className="text-mute">You’ve finished the book. <Link to="/reading" className="text-gold underline">Pick a chapter to revisit</Link>.</p>
        )}
      </div>
      <Sheet open={open && part != null} onOpenChange={setOpen} eyebrow={part ? `${view.book!.title} · part ${part.n} of ${part.of}` : ""} title={part?.chapter_title ?? ""}>
        {part && (
          <div className="space-y-6">
            <PartText part={part} />
            <div className="flex flex-wrap items-center gap-3 border-t border-line pt-6">
              <button type="button" className="pop" disabled={read.isPending} onClick={() => read.mutate(undefined, { onSuccess: () => setOpen(false) })}>
                <Check size={14} /> {read.isPending ? "Saving…" : "Done, mark as read"}
              </button>
              <Link to="/reading" className="pop pop-ghost">Open in reader <ExternalLink size={14} /></Link>
            </div>
            {read.isError && <p role="alert" className="text-sm text-coral">Couldn’t save your place. Try again.</p>}
            <Attribution view={view} />
          </div>
        )}
      </Sheet>
    </>
  );
}
