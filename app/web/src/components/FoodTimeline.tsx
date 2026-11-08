import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, Check, CloudOff, Minus, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { MEALS, servingsLabel, stepServings } from "../lib/food";
import { api } from "../lib/api";
import { groupTotals, entryRange, moveEntries, removeEntries, restoreEntries, scaleEntries } from "../lib/foodOps";
import { outbox } from "../lib/foodOutbox";
import type { LogOp } from "../lib/foodTypes";
import { rangeText } from "../lib/foodRow";
import type { FoodEntry, Meal } from "../lib/types";
import { EmptyCard } from "./EmptyState";
import type { ToastState } from "./FoodToast";
import { Card } from "./Card";

const MEAL_ORDER = MEALS.map((m) => m.value) as Meal[];
const hm = (t?: string | null) => (t ? t.slice(0, 5) : null);

/**
 * The day as a timeline grouped by meal, with ranges, queued (offline) items marked "Will sync", and a Select mode for bulk
 * delete, move, scale and save-as-meal. Every removal offers Undo.
 */
export function FoodTimeline({
  entries, queued, onAdd, onSaveMeal, onCopyDay, copying, copyNote, toast, day,
}: {
  entries: FoodEntry[];
  queued: LogOp[];
  day: string;
  onAdd: (m: Meal) => void;
  onSaveMeal: (entries: FoodEntry[], label: string) => void;
  onCopyDay: () => void;
  copying: boolean;
  copyNote: string | null;
  toast: (t: ToastState) => void;
}) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["food"] });
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [moving, setMoving] = useState(false);
  const chosen = entries.filter((e) => picked.has(e.id));
  const queuedHere = queued.filter((q) => q.day === day);

  const amount = useMutation({ mutationFn: (v: { id: number; servings: number }) => api.setFoodEntryAmount(v.id, v.servings), onSuccess: refresh });
  const run = useMutation({
    mutationFn: async (f: () => Promise<unknown>) => f(),
    onSuccess: refresh,
    onError: (e) => toast({ message: (e as Error).message || "Couldn't do that.", tone: "error" }),
  });

  const remove = (list: FoodEntry[]) =>
    run.mutate(async () => {
      await removeEntries(list);
      setPicked(new Set());
      toast({
        message: `Removed ${list.length} ${list.length === 1 ? "item" : "items"}.`,
        action: { label: "Undo", run: () => void restoreEntries(list).then(refresh).catch((e) => toast({ message: (e as Error).message, tone: "error" })) },
      });
    });

  const empty = entries.length === 0 && queuedHere.length === 0;
  if (empty) {
    return (
      <EmptyCard
        compact
        title="Nothing logged yet"
        action={<button type="button" className="chip press min-h-11" disabled={copying} onClick={onCopyDay}>Copy the day before</button>}
      >
        Type what you ate above, or tap a usual.{copyNote ? ` ${copyNote}` : ""}
      </EmptyCard>
    );
  }

  const queuedItems = queuedHere.reduce((a, q) => a + q.items.length, 0);
  return (
    <section aria-label="Day log" className="space-y-4">
      <div className="flex min-h-11 items-center justify-between gap-3 px-1">
        <p className="eyebrow">Timeline{queuedItems ? ` · includes ${queuedItems} waiting` : ""}</p>
        {entries.length > 0 && (
          <button type="button" className="chip press min-h-11" aria-pressed={selecting} onClick={() => { setSelecting(!selecting); setPicked(new Set()); setMoving(false); }}>
            {selecting ? <Check size={13} /> : null} {selecting ? "Done" : "Select"}
          </button>
        )}
      </div>

      {queuedHere.length > 0 && (
        <Card pad={false} className="divide-y divide-line">
          {queuedHere.map((q) => (
            <div key={q.key} className="flex items-start justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-bold text-cream"><CloudOff size={14} className="text-amber" /> {q.status === "needs_look" ? "Needs a look" : "Will sync"} · {MEALS.find((m) => m.value === q.meal)?.label}</p>
                <p className="truncate text-xs text-mute">{q.preview.map((p) => p.name).join(", ")}</p>
                <p className="num text-xs text-dim">{rangeText({ low: q.preview.reduce((a, p) => a + (p.low ?? 0), 0), high: q.preview.reduce((a, p) => a + (p.high ?? 0), 0) })}</p>
                {q.status === "needs_look" && <p className="text-xs text-coral">{q.error}</p>}
              </div>
              <div className="flex shrink-0 gap-1">
                {q.status === "needs_look" && <button type="button" className="chip press min-h-11" onClick={() => void outbox.retry(q.key)}>Try again</button>}
                <button type="button" className="press grid h-11 w-11 place-items-center rounded-full text-dim hover:text-coral" aria-label="Remove this waiting entry" onClick={() => void outbox.discard(q.key)}><Trash2 size={16} /></button>
              </div>
            </div>
          ))}
        </Card>
      )}

      {MEAL_ORDER.map((meal) => {
        const list = entries.filter((e) => e.meal === meal);
        if (list.length === 0) return null;
        const label = MEALS.find((m) => m.value === meal)!.label;
        const sub = groupTotals(list);
        const time = list.filter((e) => !e.eaten_at_est).map((e) => hm(e.eaten_at)).filter(Boolean).sort()[0]; // a default time is not shown as if it were real
        return (
          <Card key={meal} pad={false}>
            <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-1">
              <div className="min-w-0">
                <h2 className="t-title">{time ? `${time} ` : ""}{label}</h2>
                <p className="num text-xs text-mute">{rangeText(sub)}{sub.protein_g != null && ` · ${sub.protein_g} g protein`}</p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button type="button" className="chip press min-h-11" aria-label={`Save ${label.toLowerCase()} as a meal`} onClick={() => onSaveMeal(list, label)}><BookmarkPlus size={13} className="text-gold" /></button>
                <button type="button" className="chip press min-h-11" aria-label={`Add to ${label.toLowerCase()}`} onClick={() => onAdd(meal)}><Plus size={13} className="text-gold" /></button>
              </div>
            </div>
            <ul className="divide-y divide-line px-5 pb-2">
              {list.map((e) => (
                <EntryRow key={e.id} e={e} selecting={selecting} on={picked.has(e.id)} busy={amount.isPending || run.isPending}
                  onToggle={() => setPicked((p) => { const n = new Set(p); if (n.has(e.id)) n.delete(e.id); else n.add(e.id); return n; })}
                  onAmount={(servings) => amount.mutate({ id: e.id, servings })} onRemove={() => remove([e])} />
              ))}
            </ul>
          </Card>
        );
      })}
      {amount.isError && <p role="alert" className="text-xs text-coral">{(amount.error as Error).message}</p>}

      {selecting && (
        <div className="surface sticky bottom-24 z-30 space-y-2 p-3 md:bottom-4" role="toolbar" aria-label="Bulk actions">
          <p className="text-xs text-mute" aria-live="polite">{chosen.length === 0 ? "Tap foods to select them." : `${chosen.length} selected`}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="chip press min-h-11 disabled:opacity-40" disabled={chosen.length === 0 || run.isPending} onClick={() => remove(chosen)}><Trash2 size={13} /> Delete</button>
            <button type="button" className="chip press min-h-11 disabled:opacity-40" disabled={chosen.length === 0} aria-expanded={moving} onClick={() => setMoving(!moving)}>Move to…</button>
            {[0.5, 1.5].map((s) => (
              <button key={s} type="button" className="chip press min-h-11 disabled:opacity-40" disabled={chosen.length === 0 || run.isPending}
                onClick={() => run.mutate(async () => { const r = await scaleEntries(chosen, s); setPicked(new Set()); if (r.skipped) toast({ message: `${r.skipped} calories-only ${r.skipped === 1 ? "item has" : "items have"} no amount to scale.` }); })}>
                ×{s}
              </button>
            ))}
            <button type="button" className="chip press min-h-11 disabled:opacity-40" disabled={chosen.length === 0} onClick={() => onSaveMeal(chosen, "Selected")}>Save as meal</button>
          </div>
          {moving && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Move to meal">
              {MEALS.map((m) => (
                <button key={m.value} type="button" className="chip press min-h-11" disabled={run.isPending}
                  onClick={() => run.mutate(async () => { await moveEntries(chosen, m.value); setPicked(new Set()); setMoving(false); toast({ message: `Moved ${chosen.length} to ${m.label.toLowerCase()}.` }); })}>
                  {m.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function EntryRow({ e, selecting, on, busy, onToggle, onAmount, onRemove }: { e: FoodEntry; selecting: boolean; on: boolean; busy: boolean; onToggle: () => void; onAmount: (s: number) => void; onRemove: () => void }) {
  const range = entryRange(e);
  const adjustable = e.dish_id != null;
  const info = (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm text-paper">{e.name}</span>
      <span className="num block text-xs text-dim">
        {adjustable ? `${servingsLabel(e.servings)}× · ` : ""}{e.grams != null ? `${e.grams} g · ` : ""}{rangeText(range)}{e.protein_g != null && ` · ${e.protein_g} g protein`}
      </span>
    </span>
  );
  if (selecting) {
    return (
      <li>
        <label className="flex min-h-16 cursor-pointer items-center gap-3 py-2">
          <input type="checkbox" className="h-5 w-5" checked={on} onChange={onToggle} aria-label={`Select ${e.name}`} />
          {info}
        </label>
      </li>
    );
  }
  return (
    <li className="flex min-h-16 items-center justify-between gap-2 py-2">
      {info}
      <div className="flex shrink-0 items-center">
        {adjustable && (
          <div role="group" aria-label={`Amount of ${e.name}`} className="flex items-center">
            <button type="button" className="press grid h-11 w-11 place-items-center text-dim hover:text-paper disabled:opacity-30" aria-label={`Less ${e.name}`} disabled={busy || e.servings <= 0.5} onClick={() => onAmount(stepServings(e.servings, -1))}><Minus size={14} /></button>
            <button type="button" className="press grid h-11 w-11 place-items-center text-dim hover:text-paper disabled:opacity-30" aria-label={`More ${e.name}`} disabled={busy || e.servings >= 20} onClick={() => onAmount(stepServings(e.servings, 1))}><Plus size={14} /></button>
          </div>
        )}
        <button type="button" className="press grid h-11 w-11 place-items-center text-dim hover:text-coral" aria-label={`Remove ${e.name}`} disabled={busy} onClick={onRemove}><Trash2 size={15} /></button>
      </div>
    </li>
  );
}
