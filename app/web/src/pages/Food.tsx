import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Copy, Minus, Plus, Trash2, Utensils } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Sheet } from "../components/Sheet";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";
import { BASIS_NOTE, browseList, kcalRange, MEALS, portionPreview, proteinPosition, searchList, servingsLabel, shiftDay, SOURCE_NOTE, type PortionMode } from "../lib/food";
import { formatDate } from "../lib/format";
import type { FoodDish, FoodView, Meal } from "../lib/types";

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function FoodPage() {
  const [day, setDay] = useState(localToday);
  const [adding, setAdding] = useState<Meal | null>(null);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["food", day], queryFn: () => api.food(day) });
  const refresh = () => client.invalidateQueries({ queryKey: ["food"] });
  const remove = useMutation({ mutationFn: api.deleteFoodEntry, onSuccess: refresh });
  const copy = useMutation({ mutationFn: () => api.copyFoodDay(shiftDay(day, -1), day), onSuccess: refresh });
  const today = query.data?.today ?? localToday();

  return (
    <>
      <PageHeader eyebrow="Food log" title={<>What you <em className="text-gold">ate.</em></>}>
        <div className="flex items-center gap-1">
          <button type="button" className="chip pointer-coarse:py-2" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}>
            <ChevronLeft size={14} />
          </button>
          <span className="num min-w-32 text-center text-sm text-paper">{day === today ? "Today" : formatDate(day)}</span>
          <button type="button" className="chip pointer-coarse:py-2 disabled:opacity-30" aria-label="Next day" disabled={day >= today} onClick={() => setDay(shiftDay(day, 1))}>
            <ChevronRight size={14} />
          </button>
        </div>
      </PageHeader>

      {query.isPending ? (
        <LoadingBlock height={520} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-6">
            {query.data.entries.length === 0 && (
              <div className="surface flex flex-col items-center gap-3 p-10 text-center">
                <Utensils size={26} className="text-gold" />
                <p className="font-display text-3xl text-cream">Nothing logged for this day</p>
                <p className="max-w-md text-sm text-mute">
                  Add what you ate under a meal below. This is not the same as eating nothing, so the day stays out of your averages until it has an entry.
                </p>
                <button type="button" className="pop pop-lime mt-2 disabled:opacity-40" disabled={copy.isPending} onClick={() => copy.mutate()}>
                  <Copy size={16} /> Copy the day before
                </button>
                {copy.data?.copied === 0 && <p className="text-xs text-dim">The day before has nothing logged.</p>}
                {copy.isError && <p className="text-xs text-coral">{(copy.error as Error).message}</p>}
              </div>
            )}
            {MEALS.map((m) => {
              const items = query.data.entries.filter((e) => e.meal === m.value);
              return (
                <section key={m.value} className="surface p-5 sm:p-6">
                  <div className="flex items-center justify-between">
                    <h2 className="font-display text-2xl text-cream">{m.label}</h2>
                    <button type="button" className="chip pointer-coarse:py-2" onClick={() => setAdding(m.value)}>
                      <Plus size={12} className="text-gold" /> Add
                    </button>
                  </div>
                  {items.length > 0 && (
                    <ul className="mt-3 divide-y divide-line">
                      {items.map((e) => (
                        <li key={e.id} className="flex items-center justify-between gap-3 py-2.5">
                          <div className="min-w-0">
                            <p className="truncate text-sm text-paper">
                              {e.dish_id != null && e.servings !== 1 && <span className="num text-gold">{servingsLabel(e.servings)} × </span>}
                              {e.name}
                            </p>
                            <p className="num text-xs text-dim">
                              {e.grams != null && `${e.grams} g · `}{e.kcal} kcal{e.protein_g != null && ` · ${e.protein_g} g protein`}
                              {e.spread_pct >= 30 && " · eaten out, rough"}
                            </p>
                          </div>
                          <button
                            type="button"
                            aria-label={`Remove ${e.name}`}
                            className="p-1 text-dim hover:text-coral pointer-coarse:p-2"
                            disabled={remove.isPending}
                            onClick={() => remove.mutate(e.id)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
            {remove.isError && <p className="text-xs text-coral">{(remove.error as Error).message}</p>}
          </div>
          <Summary data={query.data} />
        </div>
      )}
      <AddFoodSheet meal={adding} day={day} recentIds={query.data?.recent_dish_ids ?? []} onClose={() => setAdding(null)} onSaved={refresh} />
    </>
  );
}

function Summary({ data }: { data: FoodView }) {
  const s = data.summary;
  const range = kcalRange(s);
  const pos = proteinPosition(s.protein_g_per_kg, data.protein_reference_g_per_kg);
  const [lo, hi] = data.protein_reference_g_per_kg;
  const peak = Math.max(1, ...data.trail.map((t) => t.kcal_high ?? 0));
  return (
    <aside className="space-y-6 lg:sticky lg:top-8 lg:self-start">
      <section className="surface p-6">
        <div className="eyebrow">Energy</div>
        {s.logged ? (
          <>
            <p className="num mt-2 font-display text-5xl text-cream">{s.kcal?.toLocaleString("en-US")}</p>
            <p className="num text-sm text-mute">kcal logged · likely {range}</p>
            <dl className="mt-5 grid grid-cols-3 gap-3 text-center">
              {[
                ["Protein", s.protein_g],
                ["Carbs", s.carbs_g],
                ["Fat", s.fat_g],
              ].map(([label, v]) => (
                <div key={label as string}>
                  <dt className="eyebrow">{label}</dt>
                  <dd className="num mt-1 text-xl text-paper">{v == null ? "—" : `${Math.round(v as number)} g`}</dd>
                </div>
              ))}
            </dl>
            {s.partial_macros && <p className="mt-3 text-xs text-dim">Some entries have calories only, so the macro totals may be low.</p>}
          </>
        ) : (
          <p className="mt-2 text-sm text-mute">Not logged. Totals appear once there is an entry.</p>
        )}
      </section>

      <section className="surface p-6">
        <div className="eyebrow">Protein per kg</div>
        {s.protein_g_per_kg != null ? (
          <>
            <p className="num mt-2 font-display text-4xl text-cream">{s.protein_g_per_kg.toFixed(2)} <span className="text-base text-mute">g/kg</span></p>
            <p className="mt-1 text-xs text-mute">
              {pos === "below" ? "Below" : pos === "above" ? "Above" : "Within"} the {lo}–{hi} g/kg reference for people who train
              {data.weight_kg ? `, using your ${data.weight_kg.toFixed(1)} kg trend weight` : ""}.
            </p>
            <p className="mt-2 text-xs text-dim">Reference: ISSN position stand, Jäger et al. 2017. A guide to compare against, not a target set for you.</p>
          </>
        ) : (
          <p className="mt-2 text-sm text-mute">
            {data.weight_kg == null ? "Needs a weigh-in to compute." : "Needs protein logged for the day."}
          </p>
        )}
      </section>

      <section className="surface p-6">
        <div className="eyebrow">Last 7 days</div>
        <div className="mt-4 flex h-20 items-end gap-2" role="img" aria-label="Logged calories for the last seven days">
          {data.trail.map((t) => (
            <div key={t.day} className="flex flex-1 flex-col items-center justify-end gap-1">
              {t.logged ? (
                <div className="w-full bg-gold/70" style={{ height: `${Math.max(6, ((t.kcal ?? 0) / peak) * 100)}%` }} title={`${formatDate(t.day)}: ${t.kcal} kcal`} />
              ) : (
                <div className="h-px w-full border-t border-dashed border-line-strong" title={`${formatDate(t.day)}: not logged`} />
              )}
            </div>
          ))}
        </div>
        {data.average ? (
          <p className="num mt-3 text-sm text-mute">
            Average {data.average.kcal.toLocaleString("en-US")} kcal (likely {Math.round(data.average.kcal_low).toLocaleString("en-US")}–
            {Math.round(data.average.kcal_high).toLocaleString("en-US")}) over {data.average.days_logged} logged days.
          </p>
        ) : (
          <p className="mt-3 text-xs text-dim">An average needs at least 4 logged days in the week. Dashed days weren't logged.</p>
        )}
      </section>

      <p className="text-xs leading-relaxed text-dim">
        These are estimates, not measurements. Dishes come from HealthifyMe's food database and are calculated from recipes found online, not lab-measured, so each dish shows its source. Check the portion and its weight before you pick: a bowl, a katori and 100 g are different amounts, and how you cook moves every number.
        Home-cooked entries carry about ±20%, eating out about ±30%.
      </p>
    </aside>
  );
}

type Tab = "library" | "quick" | "new";

function AddFoodSheet({ meal, day, recentIds, onClose, onSaved }: { meal: Meal | null; day: string; recentIds: number[]; onClose: () => void; onSaved: () => void }) {
  const [tab, setTab] = useState<Tab>("library");
  const [search, setSearch] = useState("");
  const label = MEALS.find((m) => m.value === meal)?.label ?? "";
  return (
    <Sheet open={meal != null} onOpenChange={(o) => !o && onClose()} eyebrow={formatDate(day)} title={`Add to ${label.toLowerCase()}`}>
      <div className="px-6 pb-8">
        <div role="tablist" className="mb-5 flex border border-line-strong p-1">
          {([["library", "My dishes"], ["quick", "Quick entry"], ["new", "New dish"]] as const).map(([v, l]) => (
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
        {meal && tab === "library" && <Library meal={meal} day={day} recentIds={recentIds} search={search} setSearch={setSearch} onSaved={onSaved} onDone={onClose} onAddNew={() => setTab("new")} />}
        {meal && tab === "quick" && <QuickEntry meal={meal} day={day} onSaved={onSaved} onDone={onClose} />}
        {meal && tab === "new" && <NewDish initialName={search.trim()} onCreated={(name) => { setSearch(name); setTab("library"); }} />}
      </div>
    </Sheet>
  );
}

const STEPS = [0.5, 1, 1.5, 2, 3, 4];

/** The household portions a dish can be measured in; a dish with only a weight gets its own unit as the one portion. */
const portionOptions = (d: FoodDish) => (d.portions.length ? d.portions : d.unit_g ? [{ unit: d.unit, grams: d.unit_g }] : []);

function Library({ meal, day, recentIds, search, setSearch, onSaved, onDone, onAddNew }: { meal: Meal; day: string; recentIds: number[]; search: string; setSearch: (s: string) => void; onSaved: () => void; onDone: () => void; onAddNew: () => void }) {
  const dishes = useQuery({ queryKey: ["food-dishes"], queryFn: api.foodDishes });
  const [picked, setPicked] = useState<FoodDish | null>(null);
  const [servings, setServings] = useState(1);
  const [mode, setMode] = useState<PortionMode>("servings");
  const [portionIdx, setPortionIdx] = useState(0);
  const [gramsText, setGramsText] = useState("");
  const [out, setOut] = useState(false);
  const grams = Number(gramsText.replace(",", "."));
  const gramsValid = gramsText.trim() !== "" && Number.isFinite(grams) && grams > 0 && grams <= 5000;
  const save = useMutation({
    mutationFn: () => {
      const opts = portionOptions(picked!);
      const eaten = mode === "grams" ? grams : opts.length ? opts[Math.min(portionIdx, opts.length - 1)].grams * servings : null;
      return api.addFoodEntry({ day, meal, dish_id: picked!.id, eating_out: out, ...(eaten != null ? { grams: Math.round(eaten * 10) / 10 } : { servings }) });
    },
    onSuccess: () => {
      onSaved();
      onDone();
      setPicked(null);
      setServings(1);
      setMode("servings");
      setPortionIdx(0);
      setGramsText("");
      setOut(false);
    },
  });
  const pick = (d: FoodDish) => {
    setPicked(d);
    setMode("servings");
    setPortionIdx(0);
    setGramsText(d.unit_g ? String(Math.round(d.unit_g)) : "");
  };
  const shown = useMemo(() => {
    const all = dishes.data?.dishes ?? [];
    return search.trim() ? searchList(all, search) : browseList(all, recentIds);
  }, [dishes.data, search, recentIds]);

  if (dishes.isPending) return <LoadingBlock height={240} />;
  if (dishes.isError) return <ErrorBlock error={dishes.error} retry={() => dishes.refetch()} />;

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
        <button type="button" className="text-xs text-mute hover:text-paper" onClick={() => setPicked(null)}>← Back to dishes</button>
        <p className="mt-3 font-display text-3xl text-cream">{picked.name}</p>
        <p className="text-xs text-dim">{SOURCE_NOTE[picked.source]} · {BASIS_NOTE[picked.basis]}</p>
        <p className="num mt-2 text-sm text-mute">
          per {picked.unit}: {Math.round(picked.kcal)} kcal · {picked.protein_g.toFixed(1)} g protein · {picked.carbs_g.toFixed(1)} g carbs · {picked.fat_g.toFixed(1)} g fat
        </p>
        {picked.per_100g && (
          <p className="num text-xs text-dim">
            per 100 g: {picked.per_100g.kcal} kcal · {picked.per_100g.protein_g} g protein · {picked.per_100g.carbs_g} g carbs · {picked.per_100g.fat_g} g fat
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
          ≈ {Math.round(preview.kcal)} kcal · {Math.round(preview.protein_g)} g protein{preview.grams != null && ` · ${Math.round(preview.grams)} g`}
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
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search all dishes: dal, roti, poha"
        aria-label="Search dishes"
        className="w-full border-b-2 border-line-strong bg-transparent py-2 text-lg text-paper outline-none focus:border-gold"
      />
      {shown.length === 0 && (
        <p className="mt-6 text-sm text-mute">No dish called “{search.trim()}” in your library.</p>
      )}
      {search.trim() !== "" && !shown.some((d) => d.name.toLowerCase() === search.trim().toLowerCase()) && (
        <button type="button" className="chip mt-4 pointer-coarse:py-2.5" onClick={onAddNew}>
          <Plus size={12} className="text-gold" /> Add “{search.trim()}” as a new dish
        </button>
      )}
      {shown.length > 0 && (
        <ul className="mt-3 divide-y divide-line">
          {shown.map((d) => (
            <li key={d.id}>
              <button type="button" className="flex w-full items-baseline justify-between gap-3 py-3 text-left hover:text-cream pointer-coarse:py-3.5" onClick={() => pick(d)}>
                <span className="min-w-0">
                  <span className="block truncate text-sm text-paper">
                    {!search && recentIds.includes(d.id) && <span className="mr-2 text-[10px] tracking-widest text-gold uppercase">Recent</span>}
                    {d.name}
                  </span>
                  <span className="block text-xs text-dim">{d.unit}</span>
                </span>
                <span className="num shrink-0 text-xs text-mute">{d.kcal} kcal · {d.protein_g} g P</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const field = "num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-xl text-paper outline-none focus:border-gold";

function QuickEntry({ meal, day, onSaved, onDone }: { meal: Meal; day: string; onSaved: () => void; onDone: () => void }) {
  const [name, setName] = useState("");
  const [kcal, setKcal] = useState("");
  const [protein, setProtein] = useState("");
  const k = Number(kcal);
  const p = protein.trim() === "" ? null : Number(protein);
  const valid = name.trim() !== "" && Number.isFinite(k) && k > 0 && k <= 5000 && (p == null || (Number.isFinite(p) && p >= 0 && p <= 500));
  const save = useMutation({
    mutationFn: () => api.addFoodEntry({ day, meal, name: name.trim(), kcal: k, protein_g: p }),
    onSuccess: () => {
      onSaved();
      onDone();
      setName("");
      setKcal("");
      setProtein("");
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
      <label className="eyebrow mt-5 block" htmlFor="q-protein">Protein (g), if you know</label>
      <input id="q-protein" inputMode="decimal" value={protein} onChange={(e) => setProtein(e.target.value)} className={field} placeholder="Leave blank if unsure" />
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
  const num = (s: string) => (s.trim() === "" ? 0 : Number(s));
  const kcal = Number(v.kcal);
  const gramsVal = v.grams.trim() === "" ? null : Number(v.grams.replace(",", "."));
  const valid =
    v.name.trim() !== "" && v.unit.trim() !== "" && Number.isFinite(kcal) && kcal >= 0 && kcal <= 5000 && v.kcal.trim() !== "" &&
    (gramsVal == null || (Number.isFinite(gramsVal) && gramsVal > 0 && gramsVal <= 3000)) &&
    [v.protein, v.carbs, v.fat].every((s) => Number.isFinite(num(s)) && num(s) >= 0);
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
