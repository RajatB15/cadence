import { Check, Search, Star, Tag, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MAX_NAME_LEN, alsoLine, displayName, nameSuggestions, validateMyName } from "../lib/foodNames";
import { useFoodDishes, useMyNames } from "../lib/foodNamesHook";
import { rank, type FoodIndex, type MatchVia } from "../lib/foodIndex";
import { browseList } from "../lib/food";
import type { FoodDish } from "../lib/types";
import { Sheet } from "./Sheet";

type NameDish = Pick<FoodDish, "id" | "name"> & Partial<Pick<FoodDish, "aliases" | "my_names" | "display_name" | "unit" | "kcal">>;

/** Small tag button, 44px: opens the "my name" sheet for a dish. Icon only in lists, with text where there is room. */
export function NameChip({ dish, onOpen, label = false }: { dish: NameDish; onOpen: () => void; label?: boolean }) {
  const has = (dish.my_names?.length ?? 0) > 0;
  const text = has ? "Edit my names" : "Add my name";
  return (
    <button
      type="button"
      className={`press grid min-h-11 min-w-11 shrink-0 place-items-center rounded-full border border-line text-mute hover:text-gold ${label ? "w-auto grid-flow-col gap-1.5 px-3.5 text-sm font-semibold" : ""} ${has ? "!text-gold" : ""}`}
      aria-label={`${text} for ${displayName(dish)}`}
      onClick={onOpen}
    >
      <Tag size={16} aria-hidden />
      {label && <span>{has ? "My names" : "Add my name"}</span>}
    </button>
  );
}

/** Your name first, "also: library name" beneath, and why a search matched. */
export function DishTitle({ dish, via, nameClass = "text-sm text-paper" }: { dish: NameDish; via?: MatchVia; nameClass?: string }) {
  const also = alsoLine(dish);
  return (
    <>
      <span className={`block truncate ${nameClass}`}>{displayName(dish)}</span>
      {also && <span className="block truncate text-xs text-dim">{also}</span>}
      {via && <span className={`block text-xs ${via.kind === "mine" ? "text-gold" : "text-dim"}`}>{via.kind === "mine" ? `matched your name “${via.text}”` : `matched: ${via.text}`}</span>}
    </>
  );
}

/** Add, show and remove your own names for one dish. `initial` pre-fills the box (a search the user typed). */
export function MyNameSheet({ dishId, initial = "", onClose }: { dishId: number | null; initial?: string; onClose: () => void }) {
  const dishes = useFoodDishes();
  const dish = dishes.data?.dishes.find((d) => d.id === dishId) ?? null;
  const names = useMyNames();
  const [text, setText] = useState(initial);
  const [show, setShow] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    setText(initial);
    setShow(true);
    setError(null);
    setNote(null);
  }, [dishId, initial]);

  const check = dish ? validateMyName(text, dish) : null;
  const suggestions = useMemo(() => (dish ? nameSuggestions(dish, text) : []), [dish, text]);
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : "Couldn't save that name.");

  const save = async (raw = text) => {
    if (!dish) return;
    const c = validateMyName(raw, dish);
    if (!c.ok) return setError(c.reason);
    setError(null);
    try {
      const r = await names.add(dish.id, c.name, show);
      setNote(r === "queued" ? "Saved on this phone. It will sync when you're back online." : `Saved. Searching “${c.name}” now finds this dish.`);
      setText("");
    } catch (e) {
      fail(e);
    }
  };

  return (
    <Sheet open={dishId != null} onOpenChange={(o) => !o && onClose()} eyebrow="My name" title={dish ? dish.name : "Dish"}>
      {!dish ? (
        <p className="text-sm text-mute">{dishes.isPending ? "Loading…" : "That dish is no longer in your library."}</p>
      ) : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <p className="text-sm text-mute">What do you call this at home? Type it in any spelling or script, and it will find this dish next time.</p>
          <div>
            <label htmlFor="my-name" className="eyebrow block">Your name for it</label>
            <input
              id="my-name"
              value={text}
              onChange={(e) => { setText(e.target.value); setError(null); setNote(null); }}
              maxLength={MAX_NAME_LEN + 20}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              enterKeyHint="done"
              aria-invalid={error != null}
              aria-describedby={error ? "my-name-err" : undefined}
              placeholder="e.g. meetha dahi"
              className="mt-2 min-h-11 w-full rounded-lg border border-line-strong bg-slate/50 px-3 text-base text-paper outline-none focus:border-gold"
            />
          </div>
          {suggestions.length > 0 && (
            <div>
              <p className="text-xs text-dim">Other spellings of this dish</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {suggestions.map((s) => (
                  <button key={s} type="button" className="chip press min-h-11" onClick={() => { setText(s); setError(null); }}>{s}</button>
                ))}
              </div>
            </div>
          )}
          <label className="flex min-h-11 items-center gap-3 text-sm text-mute">
            <input type="checkbox" className="h-5 w-5" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show as this (your name first, library name beneath)
          </label>
          {error && <p id="my-name-err" role="alert" className="text-sm text-coral">{error}</p>}
          {note && <p role="status" className="text-sm text-lime"><Check size={14} className="mr-1 inline" />{note}</p>}
          <button type="submit" className="pop pop-lime w-full !min-h-12 justify-center disabled:opacity-40" disabled={names.pending || !check?.ok}>
            <Tag size={16} /> {names.pending ? "Saving…" : "Save my name"}
          </button>

          <div>
            <p className="eyebrow">Your names for this dish</p>
            {(dish.my_names?.length ?? 0) === 0 ? (
              <p className="mt-2 text-sm text-dim">None yet.</p>
            ) : (
              <ul className="mt-1 divide-y divide-line">
                {dish.my_names!.map((m) => (
                  <li key={m.id} className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate py-3 text-sm text-paper">{m.name}{m.preferred && <span className="ml-2 text-xs text-gold">shown first</span>}</span>
                    <button
                      type="button"
                      className={`press grid h-11 w-11 shrink-0 place-items-center rounded-full ${m.preferred ? "text-gold" : "text-dim hover:text-gold"}`}
                      aria-pressed={!!m.preferred}
                      aria-label={m.preferred ? `Stop showing ${m.name} first` : `Show ${m.name} first`}
                      onClick={() => void names.prefer(dish.id, m.id, !m.preferred).catch(fail)}
                    >
                      <Star size={16} fill={m.preferred ? "currentColor" : "none"} />
                    </button>
                    <button type="button" className="press grid h-11 w-11 shrink-0 place-items-center rounded-full text-dim hover:text-coral" aria-label={`Remove my name ${m.name}`} onClick={() => void names.remove(dish.id, m.id).catch(fail)}>
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </form>
      )}
    </Sheet>
  );
}

/**
 * "Find it by another name": the typed text matched nothing good, so pick the dish you mean from a short list and one tap
 * remembers the text as your name for it. `onPick` gets the dish after the name was saved.
 */
export function FindByOtherName({ text, index, recentIds, onPicked, onClose }: { text: string | null; index: FoodIndex | null; recentIds: number[]; onPicked: (d: FoodDish, name: string) => void; onClose: () => void }) {
  const names = useMyNames();
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  useEffect(() => { setQ(""); setError(null); }, [text]);
  const all = useMemo(() => (index ? [...index.dishById.values()] : []) as FoodDish[], [index]);
  const list = useMemo(() => {
    if (!index) return [];
    if (q.trim()) return rank(index, q, undefined, 8).map((r) => r.dish as FoodDish);
    const loose = text ? text.split(/\s+/).flatMap((w) => rank(index, w, undefined, 3).map((r) => r.dish as FoodDish)) : [];
    const seen = new Set<number>();
    return [...loose, ...browseList(all, recentIds)].filter((d) => !seen.has(d.id) && seen.add(d.id)).slice(0, 8);
  }, [index, q, text, all, recentIds]);

  const pick = async (d: FoodDish) => {
    if (!text) return;
    const c = validateMyName(text, d);
    // Already the dish's name or one of yours: just open it.
    if (!c.ok) { onPicked(d, text); return; }
    setBusy(d.id);
    setError(null);
    try {
      await names.add(d.id, c.name, true);
      onPicked(d, c.name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that name.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Sheet open={text != null} onOpenChange={(o) => !o && onClose()} eyebrow="Find it by another name" title={`“${text ?? ""}”`}>
      <p className="text-sm text-mute">Pick the dish you mean. Cadence will remember “{text}” as your name for it, so searching it works next time.</p>
      <div className="surface mt-4 flex min-h-11 items-center gap-2 rounded-full px-4">
        <Search size={16} className="text-dim" aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search for the dish by its library name" placeholder="Search by another name" autoComplete="off" autoCapitalize="none" spellCheck={false} className="min-h-11 min-w-0 flex-1 bg-transparent text-base text-paper outline-none placeholder:text-dim" />
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-coral">{error}</p>}
      {!index ? (
        <p className="mt-4 text-sm text-dim">Your dishes are still loading.</p>
      ) : list.length === 0 ? (
        <p className="mt-4 text-sm text-dim">No dish found for “{q}”. Try another spelling.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line">
          {list.map((d) => (
            <li key={d.id}>
              <button type="button" className="press flex min-h-14 w-full items-center justify-between gap-3 py-2 text-left disabled:opacity-50" disabled={busy != null} onClick={() => void pick(d)}>
                <span className="min-w-0"><DishTitle dish={d} /></span>
                <span className="chip shrink-0 !text-gold">{busy === d.id ? "Saving…" : "Use my name"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
