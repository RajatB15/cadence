import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, Tag, ChevronRight, CloudOff, Minus, Plus, WifiOff } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Card } from "../components/Card";
import { GoalRing } from "../components/GoalRing";
import { NoteCard } from "../components/CoachNotes";
import { BarcodeSheet } from "../components/FoodBarcode";
import { ScanLabel } from "../components/FoodLabel";
import { DishTitle, FindByOtherName, MyNameSheet, NameChip } from "../components/FoodNames";
import { SavedMeals, SaveMealSheet, useSavedMeals } from "../components/FoodMeals";
import { NutrientsCard } from "../components/FoodNutrients";
import { EnergyCard, PlanNeeds, ProteinCard, WeekCard } from "../components/FoodPlan";
import { SmartEntry, useFoodDraft } from "../components/FoodSmart";
import { SuggestCard } from "../components/FoodSuggest";
import { FoodTimeline } from "../components/FoodTimeline";
import { Toast, useToast } from "../components/FoodToast";
import { Sheet } from "../components/Sheet";
import { ErrorBlock, LoadingBlock, PageHeader, Skeleton } from "../components/Shell";
import { api, ApiError, keyFor, newIdempotencyKey } from "../lib/api";
import { BASIS_NOTE, browseList, MAX_SEARCH_RESULTS, grams1, kcalRange, MEALS, portionPreview, servingsLabel, shiftDay, SOURCE_NOTE, type PortionMode } from "../lib/food";
import { chipsFromServer, localChips } from "../lib/foodChips";
import { frecencyScores, logsFromRecent, portionMemory, readHistory } from "../lib/foodFrecency";
import { ACCEPT_SCORE, buildIndex, rank } from "../lib/foodIndex";
import { alsoLine, displayName } from "../lib/foodNames";
import { useFoodDishes } from "../lib/foodNamesHook";
import { useOutbox } from "../lib/foodOutbox";
import type { FoodQuick } from "../lib/foodTypes";
import { formatDate } from "../lib/format";
import { useOnline } from "../lib/online";
import type { FoodDish, FoodEntry, FoodView, Meal } from "../lib/types";

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** The quick-logging endpoint is optional: an older server answers 404/405 and the page builds its chips from local data. */
const loadQuick = (day: string, meal: Meal): Promise<FoodQuick> =>
  api.foodQuick(day, meal).catch((e) => {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return {};
    throw e;
  });

type Manual = { meal: Meal; tab?: Tab; name?: string; nonce: number } | null;

export function FoodPage() {
  const [day, setDay] = useState(localToday);
  const [manual, setManual] = useState<Manual>(null);
  const [saving, setSaving] = useState<{ entries: FoodEntry[]; label: string } | null>(null);
  const [labelFor, setLabelFor] = useState<{ code?: string } | null>(null);
  const [barcodeOpen, setBarcodeOpen] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const client = useQueryClient();
  const online = useOnline();
  const { toast, show, dismiss } = useToast();
  const { ops } = useOutbox();
  const query = useQuery({ queryKey: ["food", day], queryFn: () => api.food(day) });
  const yesterdayQuery = useQuery({ queryKey: ["food", shiftDay(day, -1)], queryFn: () => api.food(shiftDay(day, -1)), staleTime: 60_000 });
  const dishes = useFoodDishes();
  const savedMeals = useSavedMeals();
  const refresh = () => client.invalidateQueries({ queryKey: ["food"] });
  const copy = useMutation({ mutationFn: () => api.copyFoodDay(shiftDay(day, -1), day), onSuccess: refresh });
  const today = query.data?.today ?? localToday();
  const isToday = day === today;

  const dishList = dishes.data?.dishes;
  const index = useMemo(() => (dishList ? buildIndex(dishList) : null), [dishList]);
  const draft = useFoodDraft(index, day);
  const meal = draft.meal;
  const quick = useQuery({ queryKey: ["food-quick", day, meal], queryFn: () => loadQuick(day, meal), retry: false, staleTime: 30_000 });

  const history = useMemo(() => readHistory(), [historyVersion, day]); // eslint-disable-line react-hooks/exhaustive-deps
  const recentIds = query.data?.recent_dish_ids ?? [];
  const frecency = useMemo(() => frecencyScores([...logsFromRecent(recentIds, today, meal), ...history], day, meal), [recentIds, history, today, meal, day]);
  const memory = useMemo(() => ({ ...portionMemory(history), ...Object.fromEntries(Object.entries(quick.data?.memory ?? {}).map(([k, v]) => [Number(k), v])) }), [history, quick.data]);
  const chips = useMemo(
    () =>
      chipsFromServer(quick.data) ??
      (index
        ? localChips({
            meal, today, day, history,
            dishById: index.dishById,
            yesterday: yesterdayQuery.data?.entries ?? [],
            saved: savedMeals.data?.meals ?? [],
            pinned: (dishList ?? []).filter((d) => d.pinned),
          })
        : []),
    [quick.data, index, meal, today, day, history, yesterdayQuery.data, savedMeals.data, dishList],
  );
  const dishById = index?.dishById ?? null;
  const queuedHere = ops.filter((o) => o.day === day);

  return (
    <>
      <PageHeader eyebrow="Food log" title={<>What you <em className="text-gold">ate.</em></>}>
        <div className="flex items-center gap-1">
          <button type="button" className="chip press grid min-h-11 min-w-11 place-items-center" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>
            <ChevronLeft size={16} />
          </button>
          <span className="num min-w-28 text-center text-sm text-paper">{isToday ? "Today" : formatDate(day)}</span>
          <button type="button" className="chip press grid min-h-11 min-w-11 place-items-center disabled:opacity-30" aria-label="Next day" disabled={day >= today} onClick={() => setDay(shiftDay(day, 1))}>
            <ChevronRight size={16} />
          </button>
        </div>
      </PageHeader>

      {!online && (
        <p role="status" className="surface mb-4 flex items-center gap-2 px-4 py-3 text-sm text-paper"><WifiOff size={16} className="shrink-0 text-amber" /> Offline. Entries are saved on this phone and will sync.</p>
      )}

      {query.isPending ? (
        <FoodSkeleton />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-5">
            <SummaryCard data={query.data} isToday={isToday} waiting={queuedHere.length} />
            <SmartEntry
              draft={draft}
              index={index}
              dishState={dishes.isError ? "error" : index ? "ready" : "loading"}
              onRetryDishes={() => dishes.refetch()}
              chips={chips}
              chipsLoading={quick.isPending || savedMeals.isPending}
              frecency={frecency}
              memory={memory}
              day={day}
              isToday={isToday}
              summary={query.data.summary}
              target={query.data.plan.targets?.kcal ?? null}
              onManual={() => setManual({ meal, nonce: Date.now() })}
              onScan={() => setLabelFor({})}
              onBarcode={() => setBarcodeOpen(true)}
              onNewDish={(name) => setManual({ meal, tab: "new", name, nonce: Date.now() })}
              onLogged={() => { setHistoryVersion((v) => v + 1); refresh(); client.invalidateQueries({ queryKey: ["food-quick"] }); }}
              toast={show}
            />
            <FoodTimeline
              entries={query.data.entries}
              queued={ops}
              day={day}
              onAdd={(m) => setManual({ meal: m, nonce: Date.now() })}
              onSaveMeal={(entries, label) => setSaving({ entries, label })}
              onCopyDay={() => copy.mutate()}
              copying={copy.isPending}
              copyNote={copy.data?.copied === 0 ? "The day before has nothing logged." : copy.isError ? (copy.error as Error).message : null}
              toast={show}
            />
            <SuggestCard day={day} meal={meal} dishById={dishById} onAdd={(rows) => draft.add(rows, "chip")} />
            {query.data.plan.needs.length > 0 && <PlanNeeds plan={query.data.plan} />}
            <div className="grid gap-6 md:grid-cols-2">
              <EnergyCard data={query.data} />
              <ProteinCard data={query.data} />
            </div>
          </div>
          <Aside data={query.data} />
        </div>
      )}

      <AddFoodSheet
        key={manual?.nonce ?? 0}
        meal={manual?.meal ?? null}
        day={day}
        recentIds={recentIds}
        startTab={manual?.tab}
        startName={manual?.name}
        onClose={() => setManual(null)}
        onSaved={refresh}
      />
      <SaveMealSheet
        open={saving != null}
        label={saving?.label ?? ""}
        entries={saving?.entries ?? []}
        onClose={() => setSaving(null)}
      />
      <Sheet open={labelFor != null} onOpenChange={(o) => !o && setLabelFor(null)} eyebrow={labelFor?.code ? `Barcode ${labelFor.code}` : "Packaged food"} title="Read a label">
        {!online && <p role="status" className="mb-4 text-sm text-amber">Reading a photo needs a connection to your Cadence server. You can type the numbers in once it's back.</p>}
        <ScanLabel
          meal={meal}
          day={day}
          barcode={labelFor?.code}
          onAdded={(name) => { show({ message: `Added ${name}.` }); setLabelFor(null); }}
          onSaved={() => { refresh(); client.invalidateQueries({ queryKey: ["food-dishes"] }); }}
        />
      </Sheet>
      <BarcodeSheet
        open={barcodeOpen}
        onClose={() => setBarcodeOpen(false)}
        dishById={dishById}
        onAdd={(rows) => draft.add(rows, "scan")}
        onReadLabel={(code) => { setBarcodeOpen(false); setLabelFor({ code }); }}
      />
      <Toast toast={toast} onDismiss={dismiss} />
    </>
  );
}

/** Shaped like the finished page: summary card, entry bar, chip row, three timeline rows. */
function FoodSkeleton() {
  return (
    <div className="space-y-5" role="status" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-32 rounded-[var(--radius-card)]" />
      <Skeleton className="h-14 rounded-full" />
      <div className="flex gap-2"><Skeleton className="h-11 w-36 rounded-full" /><Skeleton className="h-11 w-36 rounded-full" /><Skeleton className="h-11 w-28 rounded-full" /></div>
      {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-[var(--radius-tile)]" />)}
    </div>
  );
}

/** Kcal as a range against the day's reference, protein with unknown kept distinct from zero. Descriptive only. */
function SummaryCard({ data, isToday, waiting }: { data: FoodView; isToday: boolean; waiting: number }) {
  const s = data.summary;
  const range = kcalRange(s);
  const left = isToday ? data.plan.today?.remaining_kcal : undefined;
  return (
    <Card accent="var(--color-sky)" className="!p-5">
      <p className="eyebrow">{isToday ? "Today so far" : "That day"}</p>
      {range ? (
        <p className="numeral mt-1 text-4xl text-cream">{range}<span className="ml-1.5 text-sm font-semibold text-mute">kcal</span></p>
      ) : (
        <p className="mt-1 text-lg font-bold text-cream">Nothing logged yet</p>
      )}
      <div className="mt-5 grid grid-cols-2 gap-4">
        <GoalRing label="Calories" value={s.logged ? s.kcal : null} band={data.plan.targets?.kcal ?? null} unit="kcal" note={s.logged && data.plan.targets?.kcal == null ? "No target yet" : undefined} />
        <GoalRing label="Protein" value={s.logged ? s.protein_g : null} band={data.plan.targets?.protein_g ?? null} unit="g" note={s.logged && s.protein_g == null ? "No protein figures" : undefined} />
      </div>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mute">
        {left && <span className="num">About {Math.round(left[0]).toLocaleString("en-US")} to {Math.round(left[1]).toLocaleString("en-US")} kcal left in your range</span>}
        {s.logged && <span className="num">{s.protein_g == null ? "Protein unknown" : `${Math.round(s.protein_g)} g protein${s.partial_macros ? " (some foods unknown)" : ""}`}</span>}
        {!s.logged && !range && <span>Not the same as eating nothing: an empty day stays out of your averages.</span>}
        {waiting > 0 && <span className="inline-flex items-center gap-1 text-amber"><CloudOff size={12} /> {waiting} waiting to sync, not counted yet</span>}
      </div>
    </Card>
  );
}

function Aside({ data }: { data: FoodView }) {
  const t = data.plan.targets;
  const avg = data.average;
  return (
    <aside className="space-y-6 lg:sticky lg:top-8 lg:self-start">
      <WeekCard data={data} />

      <NutrientsCard data={data} />
      {t && <p className="text-[11px] text-dim">Fat guide {t.fat_g[0]}–{t.fat_g[1]} g a day (0.5–1.5 g/kg), the rest of the calories from carbohydrate (Iraki 2019).</p>}

      {data.notes.length > 0 && (
        <div className="space-y-3">
          {data.notes.map((f, i) => (
            <NoteCard key={f.id} f={f} index={i} compact />
          ))}
        </div>
      )}

      {avg && <p className="num text-xs text-dim">Week average {avg.kcal.toLocaleString("en-US")} kcal over {avg.days_logged} logged days (of {avg.days_covered}).</p>}
      <p className="text-xs leading-relaxed text-dim">
        These are estimates, not measurements. Dishes come from a public food database and are calculated from recipes found online, not lab-measured, so each dish shows its source.
        Check the portion and its weight before you pick: a bowl, a katori and 100 g are different amounts, and how you cook moves every number. Targets are a planning range from published
        guidance for people who train, not medical advice.
      </p>
      <Link to="/food/library" className="text-xs text-mute underline decoration-line-strong underline-offset-4 hover:text-paper">See how the food library is being built</Link>
    </aside>
  );
}

export type Tab = "meals" | "library" | "scan" | "quick" | "new";

function AddFoodSheet({ meal, day, recentIds, onClose, onSaved, startTab, startName }: { meal: Meal | null; day: string; recentIds: number[]; onClose: () => void; onSaved: () => void; startTab?: Tab; startName?: string }) {
  const [chosenTab, setTab] = useState<Tab>(startTab ?? "library");
  const [search, setSearch] = useState(startName ?? "");
  const [added, setAdded] = useState<string[]>([]);
  const saved = useSavedMeals();
  const hasMeals = (saved.data?.meals.length ?? 0) > 0;
  const tab: Tab = chosenTab === "meals" && !hasMeals ? "library" : chosenTab;
  const close = () => {
    setAdded([]);
    setSearch("");
    onClose();
  };
  const note = (name: string) => setAdded((a) => [...a, name]);
  const label = MEALS.find((m) => m.value === meal)?.label ?? "";
  return (
    <Sheet open={meal != null} onOpenChange={(o) => !o && close()} eyebrow={formatDate(day)} title={`Add to ${label.toLowerCase()}`}>
      <div className="px-6 pb-8">
        <div role="tablist" className="mb-5 flex border border-line-strong p-1">
          {([...(hasMeals ? ([["meals", "Meals"]] as const) : []), ["library", "Dishes"], ["scan", "Scan label"], ["quick", "Quick add"], ["new", "New dish"]] as const).map(([v, l]) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={tab === v}
              onClick={() => setTab(v)}
              className={`flex-1 px-2 py-1.5 text-xs font-semibold tracking-widest uppercase pointer-coarse:py-2.5 ${tab === v ? "bg-cream text-ink" : "text-mute hover:text-paper"}`}
            >
              {l}
            </button>
          ))}
        </div>
        {added.length > 0 && (
          <div className="mb-4 flex items-center justify-between gap-3 border border-line-strong bg-ink/40 px-3 py-2" role="status">
            <p className="min-w-0 truncate text-xs text-mute"><Check size={12} className="mr-1.5 inline text-lime" />Added: {added.join(", ")}</p>
            <button type="button" className="chip shrink-0 !text-gold pointer-coarse:py-2" onClick={close}>Done</button>
          </div>
        )}
        {meal && tab === "meals" && <SavedMeals meal={meal} day={day} onLogged={(name) => { note(name); onSaved(); }} />}
        {meal && tab === "library" && <Library meal={meal} day={day} recentIds={recentIds} search={search} setSearch={setSearch} onSaved={onSaved} onAdded={note} onAddNew={() => setTab("new")} />}
        {meal && tab === "scan" && <ScanLabel meal={meal} day={day} onAdded={note} onSaved={onSaved} />}
        {meal && tab === "quick" && <QuickEntry meal={meal} day={day} onSaved={onSaved} onAdded={note} />}
        {meal && tab === "new" && <NewDish initialName={search.trim()} onCreated={(name) => { setSearch(name); setTab("library"); }} />}
      </div>
    </Sheet>
  );
}

const STEPS = [0.5, 1, 1.5, 2, 3, 4];

/** The household portions a dish can be measured in; a dish with only a weight gets its own unit as the one portion. */
const portionOptions = (d: FoodDish) => (d.portions.length ? d.portions : d.unit_g ? [{ unit: d.unit, grams: d.unit_g }] : []);

function Library({ meal, day, recentIds, search, setSearch, onSaved, onAdded, onAddNew }: { meal: Meal; day: string; recentIds: number[]; search: string; setSearch: (s: string) => void; onSaved: () => void; onAdded: (name: string) => void; onAddNew: () => void }) {
  const dishes = useFoodDishes();
  const [nameFor, setNameFor] = useState<{ id: number; initial: string } | null>(null);
  const [otherFor, setOtherFor] = useState<string | null>(null);
  const [pickedRaw, setPicked] = useState<FoodDish | null>(null);
  const picked = pickedRaw ? (dishes.data?.dishes.find((d) => d.id === pickedRaw.id) ?? pickedRaw) : null;
  const [servings, setServings] = useState(1);
  const [mode, setMode] = useState<PortionMode>("servings");
  const [portionIdx, setPortionIdx] = useState(0);
  const [gramsText, setGramsText] = useState("");
  const [out, setOut] = useState(false);
  const grams = Number(gramsText.replace(",", "."));
  const gramsValid = gramsText.trim() !== "" && Number.isFinite(grams) && grams > 0 && grams <= 5000;
  const idem = useRef<{ sig: string; key: string } | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const opts = portionOptions(picked!);
      const eaten = mode === "grams" ? grams : opts.length ? opts[Math.min(portionIdx, opts.length - 1)].grams * servings : null;
      const entry = { day, meal, dish_id: picked!.id, eating_out: out, ...(eaten != null ? { grams: Math.round(eaten * 10) / 10 } : { servings }) };
      return api.addFoodEntry(entry, keyFor(idem, entry));
    },
    onSuccess: () => {
      idem.current = null;
      onSaved();
      onAdded(picked!.name);
      setPicked(null);
      setServings(1);
      setMode("servings");
      setPortionIdx(0);
      setGramsText("");
      setOut(false);
    },
  });
  // One tap on the + of a result logs one usual serving; the amount can be changed afterwards with the ± on the entry.
  const quick = useMutation({
    mutationFn: (d: FoodDish) => api.addFoodEntry({ day, meal, dish_id: d.id, servings: 1 }, newIdempotencyKey()).then(() => d),
    onSuccess: (d) => {
      onSaved();
      onAdded(d.name);
    },
  });
  const pick = (d: FoodDish) => {
    setPicked(d);
    setMode("servings");
    setPortionIdx(0);
    setGramsText(d.unit_g ? String(Math.round(d.unit_g)) : "");
  };
  const list = dishes.data?.dishes;
  const index = useMemo(() => (list ? buildIndex(list) : null), [list]);
  const frecency = useMemo(() => frecencyScores([...logsFromRecent(recentIds, day, meal), ...readHistory()], day, meal), [recentIds, day, meal]);
  const shown = useMemo(() => {
    if (!search.trim()) return (list ? browseList(list, recentIds) : []).map((dish) => ({ dish, via: undefined, score: 0 }));
    return index ? rank(index, search, frecency, MAX_SEARCH_RESULTS).map((r) => ({ ...r, dish: r.dish as FoodDish })) : [];
  }, [list, index, search, recentIds, frecency]);
  const goodMatch = shown.some((r) => r.score >= ACCEPT_SCORE * 3);

  if (dishes.isPending) return <LoadingBlock height={240} />;
  if (dishes.isError) return <ErrorBlock error={dishes.error} retry={() => dishes.refetch()} />;

  const sheets = (
    <>
      <MyNameSheet dishId={nameFor?.id ?? null} initial={nameFor?.initial ?? ""} onClose={() => setNameFor(null)} />
      <FindByOtherName
        text={otherFor}
        index={index}
        recentIds={recentIds}
        onClose={() => setOtherFor(null)}
        onPicked={(d, name) => { setOtherFor(null); setSearch(name); pick(d); }}
      />
    </>
  );

  if (picked) {
    const opts = portionOptions(picked);
    const portion = opts[Math.min(portionIdx, Math.max(opts.length - 1, 0))];
    const preview =
      mode === "grams"
        ? portionPreview(picked, "grams", gramsValid ? grams : 0)
        : portion && picked.grams_ok
          ? portionPreview(picked, "grams", portion.grams * servings)
          : portionPreview(picked, "servings", servings);
    return (
      <div>
        {sheets}
        <button type="button" className="text-xs text-mute hover:text-paper" onClick={() => setPicked(null)}>← Back to dishes</button>
        <p className="mt-3 font-display text-3xl text-cream">{displayName(picked)}</p>
        {alsoLine(picked) && <p className="text-sm text-mute">{alsoLine(picked)}</p>}
        <div className="mt-2"><NameChip dish={picked} label onOpen={() => setNameFor({ id: picked.id, initial: "" })} /></div>
        <p className="text-xs text-dim">{SOURCE_NOTE[picked.source]} · {BASIS_NOTE[picked.basis]}</p>
        <p className="num mt-2 text-sm text-mute">
          per {picked.unit}: {Math.round(picked.kcal)} kcal · protein {grams1(picked.protein_g)} · carbs {grams1(picked.carbs_g)} · fat {grams1(picked.fat_g)}
        </p>
        {picked.per_100g && (
          <p className="num text-xs text-dim">
            per 100 g: {picked.per_100g.kcal} kcal · protein {grams1(picked.per_100g.protein_g)} · carbs {grams1(picked.per_100g.carbs_g)} · fat {grams1(picked.per_100g.fat_g)}
          </p>
        )}
        {picked.note && <p className="mt-2 text-xs text-dim">{picked.note}</p>}
        {picked.aliases.length > 0 && <p className="mt-1 text-xs text-dim">Also called {picked.aliases.slice(0, 4).join(", ")}</p>}

        {picked.grams_ok && (
          <div role="radiogroup" aria-label="Amount by" className="mt-6 flex w-fit border border-line-strong p-1">
            {(["servings", "grams"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={`px-3.5 py-1.5 text-xs font-semibold tracking-widest uppercase pointer-coarse:py-2.5 ${mode === m ? "bg-cream text-ink" : "text-mute hover:text-paper"}`}
              >
                {m}
              </button>
            ))}
          </div>
        )}

        {mode === "servings" || !picked.grams_ok ? (
          <>
            {picked.grams_ok && opts.length > 1 && (
              <>
                <label className="eyebrow mt-6 block" htmlFor="portion">Portion</label>
                <select id="portion" value={portionIdx} onChange={(e) => setPortionIdx(Number(e.target.value))} className="mt-2 w-full border-b-2 border-line-strong bg-coal py-2 text-base text-paper outline-none focus:border-gold">
                  {opts.map((o, i) => (
                    <option key={`${o.unit}-${o.grams}`} value={i}>{o.unit} · {o.grams} g</option>
                  ))}
                </select>
              </>
            )}
            <div className="eyebrow mt-6">{portion && picked.grams_ok ? `How many (${portion.unit})?` : "How many?"}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button type="button" className="chip pointer-coarse:py-2" aria-label="Fewer" onClick={() => setServings(Math.max(0.25, servings - 0.25))}><Minus size={12} /></button>
              <span className="num min-w-12 text-center text-2xl text-paper">{servingsLabel(servings)}</span>
              <button type="button" className="chip pointer-coarse:py-2" aria-label="More" onClick={() => setServings(Math.min(20, servings + 0.25))}><Plus size={12} /></button>
              {STEPS.map((s) => (
                <button key={s} type="button" aria-pressed={servings === s} className={`chip pointer-coarse:py-2 ${servings === s ? "!text-gold" : ""}`} onClick={() => setServings(s)}>
                  {servingsLabel(s)}
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <label className="eyebrow mt-6 block" htmlFor="grams">Weight eaten (g)</label>
            <input id="grams" inputMode="decimal" value={gramsText} onChange={(e) => setGramsText(e.target.value)} className={field} aria-invalid={gramsText !== "" && !gramsValid} />
            <div className="mt-2 flex flex-wrap gap-2">
              {[50, 100, 150, 200, 250].map((g) => (
                <button key={g} type="button" className="chip pointer-coarse:py-2" onClick={() => setGramsText(String(g))}>{g} g</button>
              ))}
            </div>
          </>
        )}

        <label className="mt-5 flex items-center gap-2 text-sm text-mute">
          <input type="checkbox" checked={out} onChange={(e) => setOut(e.target.checked)} /> Eaten out or not home-cooked (wider range)
        </label>
        <p className="num mt-5 text-sm text-paper">
          ≈ {Math.round(preview.kcal)} kcal · {preview.protein_g == null ? "protein unknown" : `${Math.round(preview.protein_g)} g protein`}{preview.grams != null && ` · ${Math.round(preview.grams)} g`}
        </p>
        {save.isError && <p className="mt-3 text-xs text-coral">{(save.error as Error).message}</p>}
        <button type="button" className="pop pop-lime mt-6 disabled:opacity-40" disabled={save.isPending || (mode === "grams" && picked.grams_ok && !gramsValid)} onClick={() => save.mutate()}>
          <Plus size={16} /> Add
        </button>
      </div>
    );
  }

  return (
    <div>
      <input
        value={search}
        autoFocus
        enterKeyHint="search"
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search all dishes: dal, roti, poha"
        aria-label="Search dishes"
        className="w-full border-b-2 border-line-strong bg-transparent py-2 text-lg text-paper outline-none focus:border-gold"
      />
      {shown.length === 0 && search.trim() === "" && <p className="mt-6 text-sm text-mute">No dishes in your library yet. Add one under New dish.</p>}
      {search.trim() !== "" && !goodMatch && (
        <div className="surface mt-4 space-y-2 p-4" role="status">
          <p className="text-sm text-paper">{shown.length === 0 ? `No dish called “${search.trim()}” in your library.` : `Nothing close to “${search.trim()}”.`}</p>
          <p className="text-xs text-mute">Know it by another name? Pick the dish and tag it with your name, so this search works next time.</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="chip press min-h-11 !text-gold" onClick={() => setOtherFor(search.trim())}>
              <Tag size={13} /> Find it by another name
            </button>
            <button type="button" className="chip press min-h-11" onClick={onAddNew}>
              <Plus size={12} className="text-gold" /> Add “{search.trim()}” as a new dish
            </button>
          </div>
        </div>
      )}
      {sheets}
      {quick.isError && <p className="mt-3 text-xs text-coral">{(quick.error as Error).message}</p>}
      {shown.length > 0 && (
        <ul className="mt-3 divide-y divide-line">
          {shown.map(({ dish: d, via }) => (
            <li key={d.id} className="flex items-center gap-1">
              <button type="button" className="flex min-w-0 flex-1 items-baseline justify-between gap-3 py-3 text-left hover:text-cream pointer-coarse:py-3.5" onClick={() => pick(d)}>
                <span className="min-w-0">
                  {!search && recentIds.includes(d.id) && <span className="block text-[11px] tracking-widest text-gold uppercase">Recent</span>}
                  <DishTitle dish={d} via={via} />
                  <span className="block text-xs text-dim">{d.unit}</span>
                </span>
                <span className="num shrink-0 text-right text-xs text-mute">{Math.round(d.kcal)} kcal<span className="block">{d.protein_g == null ? "protein unknown" : `${Math.round(d.protein_g)} g protein`}</span></span>
              </button>
              <NameChip dish={d} onOpen={() => setNameFor({ id: d.id, initial: search.trim() && !via ? search.trim() : "" })} />
              <button
                type="button"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-line text-gold hover:border-gold disabled:opacity-40"
                aria-label={`Add one ${d.unit} of ${displayName(d)}`}
                disabled={quick.isPending}
                onClick={() => quick.mutate(d)}
              >
                <Plus size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const field = "num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-xl text-paper outline-none focus:border-gold";

function QuickEntry({ meal, day, onSaved, onAdded }: { meal: Meal; day: string; onSaved: () => void; onAdded: (name: string) => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [kcal, setKcal] = useState("");
  const [macros, setMacros] = useState({ protein: "", carbs: "", fat: "" });
  const [remember, setRemember] = useState(true);
  const k = Number(kcal);
  const m = (t: string) => (t.trim() === "" ? null : Number(t.replace(",", ".")));
  const okMacro = (t: string, cap: number) => m(t) == null || (Number.isFinite(m(t)!) && m(t)! >= 0 && m(t)! <= cap);
  const valid = name.trim() !== "" && Number.isFinite(k) && k > 0 && k <= 5000 && okMacro(macros.protein, 500) && okMacro(macros.carbs, 1000) && okMacro(macros.fat, 500);
  const idem = useRef<{ sig: string; key: string } | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const entry = { day, meal, name: name.trim(), kcal: k, protein_g: m(macros.protein), carbs_g: m(macros.carbs), fat_g: m(macros.fat), save_dish: remember };
      return api.addFoodEntry(entry, keyFor(idem, entry));
    },
    onSuccess: () => {
      idem.current = null;
      onSaved();
      if (remember) client.invalidateQueries({ queryKey: ["food-dishes"] });
      onAdded(name.trim());
      setName("");
      setKcal("");
      setMacros({ protein: "", carbs: "", fat: "" });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <form onSubmit={submit}>
      <p className="text-sm text-mute">For eating out or something not in your library. Treated as a rough estimate (about ±30%).</p>
      <label className="eyebrow mt-5 block" htmlFor="q-name">What was it?</label>
      <input id="q-name" value={name} onChange={(e) => setName(e.target.value)} className={field} placeholder="Office thali" maxLength={80} />
      <label className="eyebrow mt-5 block" htmlFor="q-kcal">Calories (kcal)</label>
      <input id="q-kcal" inputMode="numeric" value={kcal} onChange={(e) => setKcal(e.target.value)} className={field} placeholder="700" />
      <div className="mt-5 grid grid-cols-3 gap-4">
        {([["protein", "Protein (g)"], ["carbs", "Carbs (g)"], ["fat", "Fat (g)"]] as const).map(([key, label]) => (
          <div key={key}>
            <label className="eyebrow" htmlFor={`q-${key}`}>{label}</label>
            <input id={`q-${key}`} inputMode="decimal" value={macros[key]} onChange={(e) => setMacros({ ...macros, [key]: e.target.value })} className={field} placeholder="unknown" />
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-dim">Leave blank if unsure: blank means unknown, not zero.</p>
      <label className="mt-5 flex items-center gap-2 text-sm text-mute">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Remember it in my dishes, so I can pick it again
      </label>
      {save.isError && <p className="mt-3 text-xs text-coral">{(save.error as Error).message}</p>}
      <button type="submit" className="pop pop-lime mt-6 disabled:opacity-40" disabled={!valid || save.isPending}>
        <Plus size={16} /> Add
      </button>
    </form>
  );
}

function NewDish({ initialName, onCreated }: { initialName: string; onCreated: (name: string) => void }) {
  const client = useQueryClient();
  const [v, setV] = useState({ name: initialName, unit: "", grams: "", kcal: "", protein: "", carbs: "", fat: "" });
  const set = (key: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [key]: e.target.value });
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const kcal = Number(v.kcal);
  const gramsVal = v.grams.trim() === "" ? null : Number(v.grams.replace(",", "."));
  const valid =
    v.name.trim() !== "" && v.unit.trim() !== "" && Number.isFinite(kcal) && kcal >= 0 && kcal <= 5000 && v.kcal.trim() !== "" &&
    (gramsVal == null || (Number.isFinite(gramsVal) && gramsVal > 0 && gramsVal <= 3000)) &&
    [v.protein, v.carbs, v.fat].every((s) => num(s) == null || (Number.isFinite(num(s)!) && num(s)! >= 0));
  const save = useMutation({
    mutationFn: () => api.addFoodDish({ name: v.name.trim(), unit: v.unit.trim(), kcal, protein_g: num(v.protein), carbs_g: num(v.carbs), fat_g: num(v.fat), ...(gramsVal ? { grams: gramsVal } : {}) }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["food-dishes"] });
      onCreated(v.name.trim());
      setV({ name: "", unit: "", grams: "", kcal: "", protein: "", carbs: "", fat: "" });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <form onSubmit={submit}>
      <p className="text-sm text-mute">Add a dish the way you make it, for one serving unit you can count (a roti, a katori, a plate). Nutrition is for that one serving.</p>
      <label className="eyebrow mt-5 block" htmlFor="d-name">Name</label>
      <input id="d-name" value={v.name} onChange={set("name")} className={field} placeholder="Mum's rajma" maxLength={80} />
      <label className="eyebrow mt-5 block" htmlFor="d-unit">One serving is</label>
      <input id="d-unit" value={v.unit} onChange={set("unit")} className={field} placeholder="1 katori" maxLength={40} />
      <label className="eyebrow mt-5 block" htmlFor="d-grams">Weight of one serving (g), if you know it</label>
      <input id="d-grams" inputMode="decimal" value={v.grams} onChange={set("grams")} className={field} placeholder="e.g. 150 — lets you log by grams" />
      <p className="mt-1 text-xs text-dim">Use the same measure each time (a katori is about 150 g of most gravies, but weigh yours once to be sure).</p>
      <div className="mt-5 grid grid-cols-2 gap-4">
        {([["kcal", "Calories (kcal)"], ["protein", "Protein (g)"], ["carbs", "Carbs (g)"], ["fat", "Fat (g)"]] as const).map(([key, l]) => (
          <div key={key}>
            <label className="eyebrow block" htmlFor={`d-${key}`}>{l}</label>
            <input id={`d-${key}`} inputMode="decimal" value={v[key]} onChange={set(key)} className={field} />
          </div>
        ))}
      </div>
      {save.isError && <p className="mt-3 text-xs text-coral">{(save.error as Error).message}</p>}
      <button type="submit" className="pop pop-lime mt-6 disabled:opacity-40" disabled={!valid || save.isPending}>
        <Plus size={16} /> Save dish
      </button>
    </form>
  );
}
