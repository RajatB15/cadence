import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { rowsFromChip } from "../lib/foodChips";
import { rangeText, type FoodRow, type RowDish } from "../lib/foodRow";
import type { FoodSuggestion } from "../lib/foodTypes";
import type { Meal } from "../lib/types";
import { Card } from "./Card";
import { Skeleton } from "./Shell";

/**
 * "What fits now": a deterministic pick from your own history (docs/food-logging-design.md 2f). Collapsed by default; the request
 * is made only when opened. Without the endpoint the card says so instead of disappearing.
 */
export function SuggestCard({ day, meal, dishById, onAdd }: { day: string; meal: Meal; dishById: Map<number, RowDish> | null; onAdd: (rows: FoodRow[]) => void }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["food-suggest", day, meal],
    queryFn: () => api.foodSuggest(day, meal),
    enabled: open,
    retry: false,
  });
  const unsupported = q.error instanceof ApiError && (q.error.status === 404 || q.error.status === 405);
  return (
    <Card pad={false}>
      <button type="button" aria-expanded={open} className="press flex min-h-14 w-full items-center justify-between gap-3 px-5 text-left" onClick={() => setOpen(!open)}>
        <span>
          <span className="block text-sm font-bold text-cream">What fits now</span>
          <span className="block text-xs text-mute">Ideas from your own log</span>
        </span>
        <ChevronDown size={18} className={`text-mute transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-3 px-5 pb-5">
          {q.isPending && <div className="space-y-2" role="status" aria-label="Loading"><Skeleton className="h-14" /><Skeleton className="h-14" /></div>}
          {unsupported && <p className="text-sm text-mute">Suggestions aren't available on this server yet.</p>}
          {q.isError && !unsupported && <p role="alert" className="text-sm text-coral">Couldn't load suggestions. <button type="button" className="min-h-11 font-bold underline" onClick={() => q.refetch()}>Try again</button></p>}
          {q.data?.status === "insufficient" && <p className="text-sm text-mute">{q.data.reasons_note || "Log a few meals and your usuals will show up here."}</p>}
          {q.data && q.data.status !== "insufficient" && (q.data.suggestions ?? []).length === 0 && <p className="text-sm text-mute">Nothing to suggest for this meal yet. Log a few meals and your usuals will show up here.</p>}
          {(q.data?.suggestions ?? []).slice(0, 3).map((s, i) => <Suggestion key={`${s.label}:${i}`} s={s} dishById={dishById} onAdd={onAdd} />)}
          {q.data && (q.data.suggestions ?? []).length > 0 && <p className="text-[11px] text-dim">From your own log. Library values are estimates.</p>}
        </div>
      )}
    </Card>
  );
}

function Suggestion({ s, dishById, onAdd }: { s: FoodSuggestion; dishById: Map<number, RowDish> | null; onAdd: (rows: FoodRow[]) => void }) {
  const [why, setWhy] = useState(false);
  const items = (s.items ?? []).map((i) => ({ dishId: i.dish_id ?? null, name: i.name, servings: i.servings ?? 1, grams: i.grams ?? null, unit: i.unit ?? null, kcal: i.kcal, protein_g: i.protein_g }));
  const rows = dishById ? rowsFromChip({ key: s.label, kind: "suggest", label: s.label, items }, dishById) : [];
  return (
    <div className="surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-bold text-cream">{s.label}</p>
          <p className="num text-xs text-mute">{rangeText(s.kcal)}{s.protein_g != null ? ` · about ${Math.round(s.protein_g)} g protein` : ""}</p>
        </div>
        <button type="button" className="pop pop-ghost !min-h-11 shrink-0 disabled:opacity-40" disabled={rows.length === 0} onClick={() => onAdd(rows)}><Plus size={14} /> Add</button>
      </div>
      {(s.reasons ?? []).length > 0 && (
        <>
          <button type="button" aria-expanded={why} className="mt-1 min-h-11 text-xs font-bold text-gold" onClick={() => setWhy(!why)}>{why ? "Hide why" : "Why this?"}</button>
          {why && <ul className="list-disc space-y-1 pl-5 text-xs text-mute">{s.reasons!.map((r) => <li key={r}>{r}</li>)}</ul>}
        </>
      )}
    </div>
  );
}
