import { useMutation } from "@tanstack/react-query";
import { Camera, Check, FileText, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { amount, dishFromLabel, fieldsFrom, LABEL_FIELDS, type LabelColumn, type LabelFields } from "../lib/foodLabel";
import type { FoodLabelRead, Meal } from "../lib/types";
import { LoadingBlock } from "./Shell";

const field = "num mt-1 w-full border-b-2 border-line-strong bg-transparent py-1.5 text-lg text-paper outline-none focus:border-gold";
const COLUMN_LABEL: Record<LabelColumn, string> = { per_100g: "Per 100 g", per_serving: "Per serving" };

/**
 * Photograph a nutrition table, check what was read next to the photo, and save it as one of your dishes (and add it to the
 * day). Reading saves nothing; numbers can be misread, so every field is editable and unreadable ones stay blank.
 */
export function ScanLabel({ meal, day, onAdded, onSaved }: { meal: Meal; day: string; onAdded: (name: string) => void; onSaved: () => void }) {
  const [photo, setPhoto] = useState<string | null>(null);
  const [read, setRead] = useState<FoodLabelRead | null>(null);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo); }, [photo]);

  const scan = useMutation({
    mutationFn: (file: File) => api.readFoodLabel(file),
    onSuccess: setRead,
  });
  const fromText = useMutation({ mutationFn: (t: string) => api.readFoodLabelText(t), onSuccess: setRead });
  const reset = () => {
    setRead(null);
    setPhoto(null);
    setPasted("");
    scan.reset();
    fromText.reset();
  };

  if (read) {
    return <Review read={read} photo={photo} meal={meal} day={day} onBack={reset} onAdded={(n) => { onAdded(n); onSaved(); reset(); }} />;
  }
  if (scan.isPending || fromText.isPending) return <LoadingBlock height={200} />;
  const error = (scan.error ?? fromText.error) as ApiError | null;
  return (
    <div>
      <p className="text-sm text-mute">
        Photograph the nutrition table on the pack: flat, close and in good light. It's read on your server, nothing is saved until you confirm, and the dish is kept in your library for next time.
      </p>
      <input
        ref={input}
        type="file"
        accept="image/*"
        capture="environment"
        className="sr-only"
        aria-label="Photo of the nutrition label"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setPhoto(URL.createObjectURL(file));
          scan.mutate(file);
        }}
      />
      <button type="button" className="pop pop-lime mt-5" onClick={() => input.current?.click()}>
        <Camera size={16} /> Take or choose a photo
      </button>
      {error && (
        <p role="alert" className="mt-4 text-sm text-coral">
          {error.status === 501 ? "Text recognition isn't available on this server. Paste the label text below, or use Quick entry." : error.message}
        </p>
      )}
      <div className="mt-6">
        <button type="button" aria-expanded={pasting} className="chip pointer-coarse:py-2" onClick={() => setPasting(!pasting)}>
          <FileText size={12} className="text-gold" /> Paste the label text instead
        </button>
        {pasting && (
          <div className="mt-3">
            <textarea
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              rows={6}
              aria-label="Label text"
              placeholder={"Per 100 g   Per serve (30 g)\nEnergy (kcal) 389 117\nProtein 13.5 4.1"}
              className="num w-full border border-line-strong bg-transparent p-3 text-sm text-paper outline-none focus:border-gold"
            />
            <button type="button" className="chip mt-2 pointer-coarse:py-2" disabled={!pasted.trim()} onClick={() => fromText.mutate(pasted)}>Read it</button>
          </div>
        )}
      </div>
    </div>
  );
}

function Review({ read, photo, meal, day, onBack, onAdded }: { read: FoodLabelRead; photo: string | null; meal: Meal; day: string; onBack: () => void; onAdded: (name: string) => void }) {
  const columns = read.order.length ? read.order : (["per_100g"] as LabelColumn[]);
  const [basis, setBasis] = useState<LabelColumn>(columns[0]);
  const [f, setF] = useState<LabelFields>(() => fieldsFrom(read, columns[0]));
  const [name, setName] = useState("");
  const [serving, setServing] = useState(read.serving_g ? String(read.serving_g) : "");
  const servingG = amount(serving);
  const dish = dishFromLabel(name, basis, f, servingG && servingG > 0 ? servingG : null);
  const issues = read.issues[basis] ?? [];
  const pickColumn = (c: LabelColumn) => {
    setBasis(c);
    setF(fieldsFrom(read, c));
  };
  const save = useMutation({
    mutationFn: async () => {
      const created = await api.addFoodDish(dish!);
      await api.addFoodEntry({ day, meal, dish_id: created.id, servings: 1 });
      return created;
    },
    onSuccess: (d) => onAdded(d.name),
  });
  const found = Object.values(read.columns).some((c) => c && Object.keys(c).length > 0);
  return (
    <div>
      <button type="button" className="text-xs text-mute hover:text-paper" onClick={onBack}>← Start again</button>
      <div className="mt-3 grid gap-5 sm:grid-cols-[160px_minmax(0,1fr)]">
        {photo && <img src={photo} alt="The label you photographed" className="max-h-56 w-full border border-line object-contain sm:max-h-none" />}
        <div className="space-y-2">
          <p className="eyebrow">{found ? "Check what was read" : "Nothing was read"}</p>
          {read.warnings.map((w) => (
            <p key={w} className="text-xs text-amber-300" role="status">{w}</p>
          ))}
          {issues.map((w) => (
            <p key={w} className="text-xs text-coral" role="alert">{w}</p>
          ))}
          {!found && <p className="text-xs text-dim">You can still fill the numbers in by hand below.</p>}
        </div>
      </div>

      {columns.length > 1 && (
        <div role="radiogroup" aria-label="Which column did you eat by" className="mt-5 flex w-fit border border-line-strong p-1">
          {columns.map((c) => (
            <button key={c} type="button" role="radio" aria-checked={basis === c} onClick={() => pickColumn(c)}
              className={`px-3.5 py-1.5 text-xs font-semibold tracking-widest uppercase pointer-coarse:py-2.5 ${basis === c ? "bg-cream text-ink" : "text-mute hover:text-paper"}`}>
              {COLUMN_LABEL[c]}
            </button>
          ))}
        </div>
      )}
      {columns.length === 1 && <p className="mt-5 text-xs text-dim">Numbers are {COLUMN_LABEL[columns[0]].toLowerCase()}.</p>}

      <label className="eyebrow mt-5 block" htmlFor="label-name">Name</label>
      <input id="label-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Brand and product, e.g. Quaker Oats" className={field.replace("text-lg", "text-xl")} />

      <div className="mt-5 grid grid-cols-2 gap-x-5 gap-y-3">
        {LABEL_FIELDS.map(({ key, label, unit }) => (
          <div key={key}>
            <label className="eyebrow" htmlFor={`lf-${key}`}>{label} ({unit})</label>
            <input id={`lf-${key}`} inputMode="decimal" value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} aria-invalid={f[key] !== "" && amount(f[key]) == null} className={field} placeholder="unknown" />
          </div>
        ))}
        <div>
          <label className="eyebrow" htmlFor="lf-serving">One serving weighs (g)</label>
          <input id="lf-serving" inputMode="decimal" value={serving} onChange={(e) => setServing(e.target.value)} className={field} placeholder="optional" />
        </div>
      </div>
      <p className="mt-3 text-xs text-dim">
        {servingG ? "With the serving weight you can log it by grams, and fibre, sugars and sodium are tracked." : "Add the serving weight to log it by grams and to track fibre, sugars and sodium."} Blank means unknown, not zero.
      </p>
      {save.isError && <p className="mt-3 text-xs text-coral" role="alert">{(save.error as Error).message}</p>}
      <button type="button" className="pop pop-lime mt-6 disabled:opacity-40" disabled={!dish || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? <Check size={16} /> : <Plus size={16} />} Save to my dishes and add
      </button>
    </div>
  );
}
