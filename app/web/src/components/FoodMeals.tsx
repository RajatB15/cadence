import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, Check, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { servingsLabel } from "../lib/food";
import type { FoodEntry, FoodSavedMeal, Meal } from "../lib/types";
import { Sheet } from "./Sheet";
import { ErrorBlock, LoadingBlock } from "./Shell";

const SCALES = [0.5, 1, 1.5, 2];

/** Group some of today's foods under a name of your own so the whole combination is one tap next time. */
export function SaveMealSheet({ entries, label, open, onClose }: { entries: FoodEntry[]; label: string; open: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [off, setOff] = useState<Set<number>>(new Set());
  const chosen = entries.filter((e) => !off.has(e.id));
  const save = useMutation({
    mutationFn: () => api.saveFoodMeal(name.trim(), chosen.map((e) => e.id)),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["food-meals"] });
      setName("");
      setOff(new Set());
      onClose();
    },
  });
  const kcal = chosen.reduce((a, e) => a + e.kcal, 0);
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} eyebrow={label} title="Save as a meal">
      <form
        onSubmit={(ev) => {
          ev.preventDefault();
          if (name.trim() && chosen.length) save.mutate();
        }}
      >
        <label className="eyebrow block" htmlFor="meal-name">Name</label>
        <input
          id="meal-name"
          value={name}
          maxLength={80}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          placeholder="Usual breakfast, Post-run bowl…"
          className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-xl text-paper outline-none focus:border-gold"
        />
        <div className="eyebrow mt-6">Foods in it</div>
        <ul className="mt-2 divide-y divide-line">
          {entries.map((e) => (
            <li key={e.id}>
              <label className="flex cursor-pointer items-center gap-3 py-3">
                <input
                  type="checkbox"
                  checked={!off.has(e.id)}
                  onChange={() => setOff((prev) => { const n = new Set(prev); if (n.has(e.id)) n.delete(e.id); else n.add(e.id); return n; })}
                />
                <span className="min-w-0 flex-1 truncate text-sm text-paper">
                  {e.dish_id != null && e.servings !== 1 && <span className="num text-gold">{servingsLabel(e.servings)} × </span>}
                  {e.name}
                </span>
                <span className="num text-xs text-dim">{e.kcal} kcal</span>
              </label>
            </li>
          ))}
        </ul>
        <p className="num mt-3 text-sm text-mute">{chosen.length} {chosen.length === 1 ? "food" : "foods"} · {kcal} kcal</p>
        <p className="mt-1 text-xs text-dim">Each food is saved by dish and amount, so a dish you later edit updates the meal too.</p>
        {save.isError && <p className="mt-3 text-xs text-coral">{(save.error as Error).message}</p>}
        <button type="submit" className="pop pop-lime mt-6 disabled:opacity-40" disabled={!name.trim() || chosen.length === 0 || save.isPending}>
          <BookmarkPlus size={16} /> Save meal
        </button>
      </form>
    </Sheet>
  );
}

export function useSavedMeals() {
  return useQuery({ queryKey: ["food-meals"], queryFn: api.foodMeals });
}

/** One-tap logging of a saved meal, with a portion scale for bigger or smaller helpings. */
export function SavedMeals({ meal, day, onLogged }: { meal: Meal; day: string; onLogged: (name: string) => void }) {
  const client = useQueryClient();
  const meals = useSavedMeals();
  const [scale, setScale] = useState(1);
  const [done, setDone] = useState<number | null>(null);
  const log = useMutation({
    mutationFn: (m: FoodSavedMeal) => api.logFoodMeal(m.id, { day, meal, scale }).then(() => m),
    onSuccess: (m) => {
      setDone(m.id);
      onLogged(m.name);
      client.invalidateQueries({ queryKey: ["food"] });
      client.invalidateQueries({ queryKey: ["food-meals"] });
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteFoodMeal,
    onSuccess: () => client.invalidateQueries({ queryKey: ["food-meals"] }),
  });
  if (meals.isPending) return <LoadingBlock height={160} />;
  if (meals.isError) return <ErrorBlock error={meals.error} retry={() => meals.refetch()} />;
  const list = meals.data.meals;
  if (list.length === 0) {
    return <p className="text-sm text-mute">No saved meals yet. Log a few foods, then use “Save as meal” on that meal to group them under a name.</p>;
  }
  return (
    <div>
      <div role="radiogroup" aria-label="Portion size" className="flex flex-wrap items-center gap-2">
        <span className="eyebrow mr-1">Portions</span>
        {SCALES.map((s) => (
          <button key={s} type="button" role="radio" aria-checked={scale === s} className={`chip pointer-coarse:py-2 ${scale === s ? "!text-gold" : ""}`} onClick={() => setScale(s)}>
            {s === 1 ? "usual" : `${servingsLabel(s)}×`}
          </button>
        ))}
      </div>
      <ul className="mt-4 divide-y divide-line">
        {list.map((m) => (
          <li key={m.id} className="flex items-start justify-between gap-3 py-3.5">
            <div className="min-w-0">
              <p className="truncate text-sm text-paper">{m.name}</p>
              <p className="truncate text-xs text-dim">{m.items.map((i) => i.name).join(" · ")}</p>
              <p className="num text-xs text-mute">
                {Math.round(m.kcal * scale)} kcal · {Math.round(m.protein_g * scale)} g protein{m.partial_macros && " (some macros unknown)"}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button type="button" className="chip pointer-coarse:py-2" disabled={log.isPending} onClick={() => log.mutate(m)}>
                {done === m.id && !log.isPending ? <Check size={12} className="text-lime" /> : null} {done === m.id && !log.isPending ? "Added" : "Add"}
              </button>
              <button
                type="button"
                aria-label={`Delete meal ${m.name}`}
                className="p-1 text-dim hover:text-coral pointer-coarse:p-2"
                disabled={remove.isPending}
                onClick={() => window.confirm(`Delete the saved meal “${m.name}”? Logged days keep their entries.`) && remove.mutate(m.id)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </li>
        ))}
      </ul>
      {log.isError && <p className="mt-3 text-xs text-coral">{(log.error as Error).message}</p>}
    </div>
  );
}
