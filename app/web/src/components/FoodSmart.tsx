import { Camera, ChevronDown, Clock, Minus, Plus, ScanLine, Tag, Trash2, Utensils } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api, ApiError, keyFor } from "../lib/api";
import { MEALS, servingsLabel } from "../lib/food";
import { rowsFromChip, type Chip } from "../lib/foodChips";
import { mealForTime, recordHistory } from "../lib/foodFrecency";
import { parseLine, rowForDish, type FoodIndex } from "../lib/foodIndex";
import { outbox } from "../lib/foodOutbox";
import {
  cycleUnit, loggable, rangeText, rowNutrition, rowUnitLabel, setAmount, settle, stepRow, toLogItem, totals, unitChoices,
  type FoodRow, type RowDish, type RowFlag,
} from "../lib/foodRow";
import type { LogOp } from "../lib/foodTypes";
import type { FoodDaySummary, Meal } from "../lib/types";
import { alsoLine, displayName } from "../lib/foodNames";
import { FindByOtherName, MyNameSheet, NameChip } from "./FoodNames";
import { Sheet } from "./Sheet";
import { Segmented } from "./Shell";

// ---- draft state --------------------------------------------------------------------------------------------------------

const DRAFT_KEY = "cadence.food.draft";

interface StoredDraft {
  day: string;
  meal: Meal;
  rows: Omit<FoodRow, "dish">[];
}

function readDraft(): StoredDraft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    const d = raw ? JSON.parse(raw) : null;
    return d && typeof d.day === "string" && Array.isArray(d.rows) ? d : null;
  } catch {
    return null;
  }
}

function writeDraft(d: StoredDraft | null) {
  try {
    if (d && d.rows.length) localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
    else localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* storage unavailable: the draft just lives in memory */
  }
}

/** The itemised draft. It survives a reload (localStorage, guarded) and is rebuilt against the loaded dish list. */
export function useFoodDraft(index: FoodIndex | null, day: string) {
  const [rows, setRows] = useState<FoodRow[]>(() => (readDraft()?.day === day ? (readDraft()!.rows.map((r) => ({ ...r, dish: null })) as FoodRow[]) : []));
  const [open, setOpen] = useState(false);
  const [meal, setMeal] = useState<Meal>(() => readDraft()?.meal ?? mealForTime(new Date()));
  const mealTouched = useRef(false);
  const source = useRef<string | null>(null); // "chip" or "scan" once a suggestion fed the draft; otherwise left to the server default
  useEffect(() => {
    if (!index) return;
    setRows((rs) => (rs.some((r) => r.kind === "dish" && !r.dish) ? rs.flatMap((r) => (r.kind === "dish" && !r.dish ? (index.byId.get(r.dishId ?? -1) ? [settle({ ...r, dish: index.byId.get(r.dishId!)!.dish })] : []) : [r])) : rs));
  }, [index]);
  useEffect(() => {
    writeDraft({ day, meal, rows: rows.map(({ dish: _d, ...r }) => r) });
  }, [rows, day, meal]);
  const pickMeal = useCallback((m: Meal) => {
    mealTouched.current = true;
    setMeal(m);
  }, []);
  const add = useCallback((more: FoodRow[], from?: "chip" | "scan") => {
    if (more.length === 0) return;
    if (from) source.current = from;
    setRows((r) => [...r, ...more]);
    setOpen(true);
  }, []);
  return { rows, setRows, open, setOpen, meal, pickMeal, add, source, clear: () => { source.current = null; setRows([]); } };
}

export type FoodDraft = ReturnType<typeof useFoodDraft>;

// ---- the entry bar ------------------------------------------------------------------------------------------------------

const FLAG_TEXT: Partial<Record<RowFlag, string>> = {
  rough: "Unit converted, rough",
  unit_assumed: "Unit assumed",
  unit_unknown: "Unit not recognised, counted as servings",
  ml_assumed: "ml counted as g",
  no_grams: "No weight for this dish, counted as servings",
  zero: "Amount can't be zero",
  check_amount: "Check amount",
};

export function SmartEntry({
  draft, index, dishState, onRetryDishes, chips, chipsLoading, frecency, memory, day, isToday, summary, target, onManual, onScan, onBarcode, onNewDish, onLogged, toast,
}: {
  draft: FoodDraft;
  index: FoodIndex | null;
  dishState: "loading" | "error" | "ready";
  onRetryDishes: () => void;
  chips: Chip[];
  chipsLoading: boolean;
  frecency: Map<number, number>;
  memory: Record<number, { servings: number; unit?: string | null } | undefined>;
  day: string;
  isToday: boolean;
  summary: FoodDaySummary | null;
  target: [number, number] | null;
  onManual: () => void;
  onScan: () => void;
  onBarcode: () => void;
  onNewDish: (name: string) => void;
  onLogged: () => void;
  toast: (t: import("./FoodToast").ToastState) => void;
}) {
  const [text, setText] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [mealOpen, setMealOpen] = useState(false);
  const [time, setTime] = useState("");
  const live = useMemo(() => (index && text.trim() ? parseLine(text, index, { frecency, memory }) : []), [index, text, frecency, memory]);
  const draftTotals = useMemo(() => totals(draft.rows), [draft.rows]);
  const mealLabel = MEALS.find((m) => m.value === draft.meal)?.label ?? "";

  const commit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!text.trim()) return;
    if (live.length === 0) {
      setHint("Nothing to add yet. Try “idli 2, sambar, coffee”.");
      return;
    }
    setHint(null);
    draft.add(live);
    setText("");
  };

  const chipsRowRef = useRef<HTMLDivElement>(null);
  const inputDisabled = dishState !== "ready";

  return (
    <div className="space-y-3">
      <form onSubmit={commit} className="surface flex min-h-14 items-center gap-1 rounded-full py-1 pr-1 pl-5">
        <input
          value={text}
          onChange={(e) => { setText(e.target.value); setHint(null); }}
          enterKeyHint="done"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          disabled={inputDisabled}
          aria-label="Type what you ate"
          placeholder={dishState === "loading" ? "Loading your dishes…" : "idli 2, sambar, coffee"}
          className="min-w-0 flex-1 bg-transparent py-3 text-base text-paper outline-none placeholder:text-dim disabled:opacity-60"
        />
        <button type="button" className="press grid h-11 w-11 shrink-0 place-items-center rounded-full text-mute hover:text-paper" aria-label="Scan a barcode" onClick={onBarcode}>
          <ScanLine size={20} />
        </button>
        <button type="button" className="press grid h-11 w-11 shrink-0 place-items-center rounded-full text-mute hover:text-paper" aria-label="Read a nutrition label" onClick={onScan}>
          <Camera size={20} />
        </button>
        <button type="submit" className="pop pop-lime !min-h-11 shrink-0 !px-4 disabled:opacity-40" disabled={inputDisabled || !text.trim()}>
          <Plus size={16} /> Add
        </button>
      </form>

      {dishState === "error" && (
        <p role="alert" className="px-1 text-sm text-coral">
          Your dishes didn't load, so typing can't match them yet.{" "}
          <button type="button" className="min-h-11 px-1 font-bold underline" onClick={onRetryDishes}>Try again</button> or <button type="button" className="min-h-11 px-1 font-bold underline" onClick={onManual}>add by hand</button>.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 px-1">
        <button type="button" aria-expanded={mealOpen} className="chip press min-h-11 text-sm" onClick={() => setMealOpen(!mealOpen)}>
          <Clock size={13} className="text-gold" /> {mealLabel}{isToday ? ` · ${time || "now"}` : ""} <ChevronDown size={13} className={mealOpen ? "rotate-180" : ""} />
        </button>
        <button type="button" className="chip press min-h-11 text-sm" onClick={onManual}>
          <Utensils size={13} className="text-gold" /> Add by hand
        </button>
      </div>
      {mealOpen && (
        <div className="surface flex flex-wrap items-center gap-3 p-3">
          <Segmented<Meal> label="Meal" options={MEALS.map((m) => ({ value: m.value, label: m.label }))} value={draft.meal} onChange={draft.pickMeal} />
          {isToday && (
            <label className="flex items-center gap-2 text-sm text-mute">
              Time
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="num min-h-11 rounded-lg border border-line-strong bg-slate/50 px-2 text-paper" />
            </label>
          )}
        </div>
      )}

      {chips.length > 0 ? (
        <div ref={chipsRowRef} role="list" aria-label="Suggestions" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
          {chips.map((c) => (
            <ChipButton key={c.key} chip={c} onTap={(rows) => draft.add(rows, "chip")} dishById={index?.dishById ?? null} />
          ))}
        </div>
      ) : chipsLoading ? (
        <div aria-hidden className="skeleton h-11 rounded-full" />
      ) : (
        <p className="px-1 text-sm text-dim">Your usual meals show up here after you've logged a few.</p>
      )}

      <div aria-live="polite" className="px-1">
        {hint && <p className="text-sm text-mute">{hint}</p>}
        {live.length > 0 && (
          <ul className="space-y-1">
            {live.map((r) => (
              <li key={r.id} className="flex items-baseline justify-between gap-3 text-sm">
                {r.kind === "none" ? (
                  <span className="text-mute">No dish called “{r.text}”. Add calories only, or save it as a new dish.</span>
                ) : (
                  <>
                    <span className="min-w-0 truncate text-paper">
                      {r.kind === "dish" ? displayName(r.dish!) : r.text}<span className="text-dim"> · {amountText(r)}</span>
                      {r.via && <span className={`block truncate text-xs ${r.via.kind === "mine" ? "text-gold" : "text-dim"}`}>{r.via.kind === "mine" ? `matched your name “${r.via.text}”` : `matched: ${r.via.text}`}</span>}
                    </span>
                    <span className="num shrink-0 text-xs text-mute">{rangeText(rowNutrition(r).kcal)}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {draft.rows.length > 0 && !draft.open && (
        <button type="button" className="surface press flex min-h-14 w-full items-center justify-between gap-3 px-5 text-left" onClick={() => draft.setOpen(true)}>
          <span>
            <span className="block text-sm font-bold text-cream">Your meal · {draft.rows.length} {draft.rows.length === 1 ? "item" : "items"}</span>
            <span className="num block text-xs text-mute">{rangeText(draftTotals.kcal) || "Not logged yet"}</span>
          </span>
          <span className="pop pop-ghost !min-h-11 pointer-events-none">Review</span>
        </button>
      )}

      <DraftSheet
        draft={draft}
        index={index}
        day={day}
        isToday={isToday}
        time={time}
        summary={summary}
        target={target}
        onNewDish={onNewDish}
        onLogged={() => { onLogged(); setText(""); }}
        toast={toast}
      />
    </div>
  );
}

/** "2 piece" / "150 g" / "450 kcal": what the row will log, in its own unit. */
export function amountText(r: FoodRow): string {
  if (r.kind === "kcal") return `${r.kcal} kcal`;
  if (r.kind !== "dish") return r.qty != null ? String(r.qty) : "";
  return `${servingsLabel(r.amount)} ${rowUnitLabel(r)}`.trim();
}

function ChipButton({ chip, onTap, dishById }: { chip: Chip; onTap: (rows: FoodRow[]) => void; dishById: Map<number, RowDish> | null }) {
  const rows = useMemo(() => (dishById ? rowsFromChip(chip, dishById) : []), [chip, dishById]);
  const kcal = chip.kcal ?? totals(rows).kcal;
  return (
    <button
      type="button"
      role="listitem"
      className="chip press flex min-h-11 shrink-0 flex-col items-start justify-center !rounded-2xl px-4 py-1.5 text-left"
      disabled={rows.length === 0}
      onClick={() => onTap(rowsFromChip(chip, dishById!))}
    >
      <span className="text-sm font-bold text-cream">{chip.label}</span>
      <span className="num text-xs text-dim">{chip.items.length} {chip.items.length === 1 ? "item" : "items"}{kcal ? ` · ${rangeText(kcal)}` : ""}</span>
    </button>
  );
}

// ---- the draft sheet ----------------------------------------------------------------------------------------------------

function DraftSheet({
  draft, index, day, isToday, time, summary, target, onNewDish, onLogged, toast,
}: {
  draft: FoodDraft;
  index: FoodIndex | null;
  day: string;
  isToday: boolean;
  time: string;
  summary: FoodDaySummary | null;
  target: [number, number] | null;
  onNewDish: (name: string) => void;
  onLogged: () => void;
  toast: (t: import("./FoodToast").ToastState) => void;
}) {
  const { rows, setRows } = draft;
  const [out, setOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const slot = useRef<{ sig: string; key: string } | null>(null);
  const [nameFor, setNameFor] = useState<number | null>(null);
  const [findFor, setFindFor] = useState<{ rowId: string; text: string } | null>(null);
  const t = useMemo(() => totals(rows), [rows]);
  const blocking = rows.filter((r) => !loggable(r));
  const items = rows.map((r) => toLogItem(r));
  const mealLabel = MEALS.find((m) => m.value === draft.meal)?.label ?? "";
  const patch = (id: string, f: (r: FoodRow) => FoodRow) => setRows((rs) => rs.map((r) => (r.id === id ? f(r) : r)));

  const confirm = async () => {
    if (busy || blocking.length || items.some((i) => i == null)) return;
    setBusy(true);
    setError(null);
    const payload = { day, meal: draft.meal, eaten_at: isToday ? time || nowHm() : null, eating_out: out || undefined, items: items as NonNullable<(typeof items)[number]>[] };
    const key = keyFor(slot, payload); // the same draft keeps the same key through retries
    const op: LogOp = {
      key, ...payload, source: draft.source.current ?? undefined, created_at: Date.now(), attempts: 0, status: "queued",
      preview: rows.map((r) => ({ name: r.kind === "dish" ? displayName(r.dish!) : r.text, low: rowNutrition(r).kcal?.low ?? null, high: rowNutrition(r).kcal?.high ?? null })),
    };
    try {
      const res = await outbox.submit(op);
      recordHistory(rows.filter((r) => r.kind === "dish" && r.dishId != null && r.servings != null).map((r) => ({ day, meal: draft.meal, dishId: r.dishId!, servings: r.servings!, unit: rowUnitLabel(r) })));
      const n = rows.length;
      slot.current = null;
      draft.clear();
      draft.setOpen(false);
      setOut(false);
      onLogged();
      if (res.status === "queued") {
        toast({ message: "Saved on this phone. It will sync when you're back online.", action: { label: "Undo", run: () => void outbox.discard(key) } });
      } else {
        const ids = res.ids;
        toast({ message: `Logged ${n} ${n === 1 ? "item" : "items"} to ${mealLabel.toLowerCase()}.`, action: ids.length ? { label: "Undo", run: () => void undoLogged(ids).then(onLogged) } : undefined });
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save");
    } finally {
      setBusy(false);
    }
  };

  const dayLine = daySummaryLine(summary, t, target, isToday);

  return (
    <Sheet open={draft.open && rows.length > 0} onOpenChange={draft.setOpen} eyebrow={`${isToday ? "Today" : day} · ${mealLabel}`} title="Your meal">
      <div className="-mt-2 space-y-4 pb-2">
        <Segmented<Meal> label="Meal for this draft" options={MEALS.map((m) => ({ value: m.value, label: m.label }))} value={draft.meal} onChange={draft.pickMeal} />
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <DraftRow
              key={r.id}
              row={r}
              index={index}
              onChange={(f) => patch(r.id, f)}
              onRemove={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}
              onNewDish={() => { draft.setOpen(false); onNewDish(r.text); }}
              onName={(id) => setNameFor(id)}
              onFind={() => setFindFor({ rowId: r.id, text: r.text })}
            />
          ))}
        </ul>
        <label className="flex min-h-11 items-center gap-3 text-sm text-mute">
          <input type="checkbox" className="h-5 w-5" checked={out} onChange={(e) => setOut(e.target.checked)} /> Eaten out or not home-cooked (wider range)
        </label>
        <div className="surface p-4" aria-live="polite">
          <p className="eyebrow">This meal</p>
          <p className="num mt-1 text-2xl font-extrabold text-cream">{t.kcal ? rangeText(out ? widen(t.kcal) : t.kcal) : "—"}</p>
          <p className="num text-xs text-mute">{t.protein_g == null ? "protein unknown" : `about ${t.protein_g} g protein${t.partial ? ", some items unknown" : ""}`}</p>
          {dayLine && <p className="mt-2 text-xs text-mute">{dayLine}</p>}
          <p className="mt-2 text-[11px] text-dim">Amounts are estimates, usually within 10 to 25%.</p>
        </div>
        {error && <p role="alert" className="text-sm text-coral">{error.replace(/[.\s]*$/, ".")} Your draft is kept.</p>}
        {blocking.length > 0 && <p className="text-xs text-amber">Fix or remove {blocking.length} {blocking.length === 1 ? "item" : "items"} to log.</p>}
        <button type="button" className="pop pop-lime w-full !min-h-12 justify-center disabled:opacity-40" disabled={busy || blocking.length > 0 || rows.length === 0} onClick={() => void confirm()}>
          {busy ? "Saving…" : `Confirm & log ${rows.length} ${rows.length === 1 ? "item" : "items"}${t.kcal ? ` · ${rangeText(out ? widen(t.kcal) : t.kcal)}` : ""}`}
        </button>
      </div>
      <MyNameSheet dishId={nameFor} onClose={() => setNameFor(null)} />
      <FindByOtherName
        text={findFor?.text ?? null}
        index={index}
        recentIds={[]}
        onClose={() => setFindFor(null)}
        onPicked={(d) => {
          const row = findFor;
          setFindFor(null);
          const full = index?.byId.get(d.id)?.dish ?? d;
          if (row) patch(row.rowId, (r) => rowForDish(r, full));
        }}
      />
    </Sheet>
  );
}

const nowHm = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

const widen = (k: { value: number; low: number; high: number }) => ({ value: k.value, low: Math.round(k.low - k.value * 0.1), high: Math.round(k.high + k.value * 0.1) });

/** What the day looks like with this meal added; descriptive only, never praise or blame. */
export function daySummaryLine(summary: FoodDaySummary | null, t: { kcal: { low: number; high: number } | null }, target: [number, number] | null, isToday: boolean): string | null {
  if (!t.kcal) return null;
  const known = summary?.logged && summary.kcal_low != null && summary.kcal_high != null;
  const low = (known ? summary!.kcal_low! : 0) + t.kcal.low;
  const high = (known ? summary!.kcal_high! : 0) + t.kcal.high;
  const f = (n: number) => Math.round(n).toLocaleString("en-US");
  const sofar = `${isToday ? "Today so far" : "The day"} would be ${f(low)} to ${f(high)} kcal${known ? "" : " with just this"}.`;
  return target ? `${sofar} Your range for the day is ${f(target[0])} to ${f(target[1])}.` : sofar;
}

async function undoLogged(ids: number[]): Promise<void> {
  try {
    if (ids.length > 1) await api.foodBulk({ ids, action: "delete" });
    else await api.deleteFoodEntry(ids[0]);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405) && ids.length > 1) for (const id of ids) await api.deleteFoodEntry(id).catch(() => undefined);
    else throw e;
  }
}

function DraftRow({ row, index, onChange, onRemove, onNewDish, onName, onFind }: { row: FoodRow; index: FoodIndex | null; onChange: (f: (r: FoodRow) => FoodRow) => void; onRemove: () => void; onNewDish: () => void; onName: (dishId: number) => void; onFind: () => void }) {
  const nut = rowNutrition(row);
  const dish = row.kind === "dish" && row.dish ? (index?.byId.get(row.dish.id)?.dish ?? row.dish) : null; // the live copy, so a new name shows at once
  const name = dish ? displayName(dish) : row.text;
  const [kcalText, setKcalText] = useState("");
  const choices = unitChoices(row);
  const remove = (
    <button type="button" className="press grid h-11 w-11 shrink-0 place-items-center rounded-full text-dim hover:text-coral" aria-label={`Remove ${name}`} onClick={onRemove}>
      <Trash2 size={16} />
    </button>
  );

  if (row.kind === "none") {
    const kcal = Number(kcalText);
    return (
      <li className="space-y-2 py-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm text-mute">No dish called “{row.text}”. Add calories only, or save it as a new dish.</p>
          {remove}
        </div>
        {row.candidates.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-dim">Did you mean</span>
            {row.candidates.map((c) => (
              <button key={c.id} type="button" className="chip press min-h-11" onClick={() => { const d = index?.byId.get(c.id)?.dish; if (d) onChange((r) => rowForDish(r, d)); }}>
                {c.name}?
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <input
            inputMode="numeric"
            value={kcalText}
            onChange={(e) => setKcalText(e.target.value.replace(/[^\d]/g, ""))}
            aria-label={`Calories for ${row.text}`}
            placeholder="kcal"
            className="num min-h-11 w-24 rounded-lg border border-line-strong bg-slate/50 px-3 text-paper"
          />
          <button type="button" className="chip press min-h-11 disabled:opacity-40" disabled={!(kcal > 0 && kcal <= 5000)} onClick={() => onChange((r) => settle({ ...r, kind: "kcal", kcal, flags: [], portionIdx: -2, amount: 1 }))}>
            Add calories only
          </button>
          <button type="button" className="chip press min-h-11 !text-gold" onClick={onFind}><Tag size={13} /> Find it by another name</button>
          <button type="button" className="chip press min-h-11" onClick={onNewDish}>Save as a new dish</button>
        </div>
      </li>
    );
  }

  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-base font-bold text-cream">{name}</p>
          {dish && alsoLine(dish) && <p className="truncate text-xs text-dim">{alsoLine(dish)}</p>}
          {row.kind === "dish" && row.via && <p className={`truncate text-xs ${row.via.kind === "mine" ? "text-gold" : "text-dim"}`}>{row.via.kind === "mine" ? `matched your name “${row.via.text}”` : `matched: ${row.via.text}`}</p>}
          <p className="num text-xs text-mute">
            {rangeText(nut.kcal) || "—"}{nut.protein_g != null ? ` · ${nut.protein_g} g protein` : row.kind === "dish" ? " · protein unknown" : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center">
          {dish && <NameChip dish={dish} onOpen={() => onName(dish.id)} />}
          {remove}
        </div>
      </div>
      {row.kind === "kcal" ? (
        <div className="mt-2 flex items-center gap-2">
          <Stepper label={`Less calories for ${name}`} onClick={() => onChange((r) => settle({ ...r, kcal: Math.max(50, (r.kcal ?? 0) - 50) }))} icon={<Minus size={16} />} />
          <input
            inputMode="numeric"
            aria-label={`Calories for ${name}`}
            value={row.kcal ?? ""}
            onChange={(e) => onChange((r) => settle({ ...r, kcal: Number(e.target.value.replace(/[^\d]/g, "")) || 0, flags: [] }))}
            className="num min-h-11 w-24 rounded-lg border border-line-strong bg-slate/50 px-3 text-center text-paper"
          />
          <Stepper label={`More calories for ${name}`} onClick={() => onChange((r) => settle({ ...r, kcal: (r.kcal ?? 0) + 50 }))} icon={<Plus size={16} />} />
          <span className="text-xs text-dim">kcal, a rough estimate</span>
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Stepper label={`Less ${name}`} onClick={() => onChange((r) => stepRow(r, -1))} icon={<Minus size={16} />} />
          <input
            inputMode="decimal"
            aria-label={`Amount of ${name}`}
            value={String(row.amount)}
            onChange={(e) => { const v = Number(e.target.value.replace(",", ".")); if (e.target.value !== "" && Number.isFinite(v)) onChange((r) => setAmount(r, v)); }}
            className="num min-h-11 w-16 rounded-lg border border-line-strong bg-slate/50 px-2 text-center text-paper"
          />
          <Stepper label={`More ${name}`} onClick={() => onChange((r) => stepRow(r, 1))} icon={<Plus size={16} />} />
          <button type="button" className="chip press min-h-11" disabled={choices.length < 2} onClick={() => onChange((r) => cycleUnit(r))} aria-label={`Unit: ${rowUnitLabel(row)}. Tap to change`}>
            {rowUnitLabel(row)}
          </button>
        </div>
      )}
      {row.kind === "dish" && row.grams != null && row.portionIdx >= 0 && <p className="num mt-1 text-xs text-dim">{servingsLabel(row.amount)} {rowUnitLabel(row)} is about {Math.round(row.grams)} g</p>}
      {row.kind === "dish" && row.dish && <p className="mt-1 text-[11px] text-dim">{row.dish.basis === "label" ? "From a product label you checked" : row.dish.source === "mine" ? "Your own dish" : "Estimate from a web recipe"}</p>}
      {row.flags.map((f) => (FLAG_TEXT[f] ? <p key={f} className={`mt-1 text-xs ${f === "zero" || f === "check_amount" ? "text-amber" : "text-mute"}`}>{FLAG_TEXT[f]}</p> : null))}
    </li>
  );
}

function Stepper({ label, onClick, icon }: { label: string; onClick: () => void; icon: React.ReactNode }) {
  return (
    <button type="button" className="chip press grid h-11 w-11 shrink-0 place-items-center !p-0" aria-label={label} onClick={onClick}>
      {icon}
    </button>
  );
}
