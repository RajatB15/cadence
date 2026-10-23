import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";

const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function LogWeightDialog({ hintKg, defaultOpen = false, label = "Log weight" }: { hintKg?: number | null; defaultOpen?: boolean; label?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  const [day, setDay] = useState(localToday);
  const [value, setValue] = useState("");
  const client = useQueryClient();
  const entries = useQuery({ queryKey: ["weight-entries"], queryFn: api.weightEntries, enabled: open });
  const today = entries.data?.today ?? localToday();
  const refresh = () => ["weight", "weight-entries", "overview"].forEach((k) => client.invalidateQueries({ queryKey: [k] }));
  const save = useMutation({
    mutationFn: (kg: number) => api.addWeight(day, kg),
    onSuccess: () => {
      refresh();
      setValue("");
    },
  });
  const remove = useMutation({ mutationFn: api.deleteWeight, onSuccess: refresh });

  const parsed = Number(value.replace(",", "."));
  const valid = value.trim() !== "" && Number.isFinite(parsed) && parsed >= 30 && parsed <= 300 && day !== "" && day <= today;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate(Math.round(parsed * 100) / 100);
  };
  const existing = entries.data?.entries.find((e) => e.day === day);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className="pop pop-lime">
        <Plus size={16} /> {label}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="surface fixed top-1/2 left-1/2 z-50 max-h-[92dvh] w-[min(92vw,460px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto p-8">
          <Dialog.Close className="absolute top-4 right-4 p-1 text-mute hover:text-paper" aria-label="Close">
            <X size={18} />
          </Dialog.Close>
          <Dialog.Title className="font-display text-4xl text-cream">Log your weight</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-mute">
            One reading per day — logging a day again corrects it. Garmin weigh-ins sync in on their own.
          </Dialog.Description>
          <form onSubmit={submit} className="mt-8">
            <label className="eyebrow" htmlFor="log-kg">Weight (kg)</label>
            <input
              id="log-kg"
              inputMode="decimal"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-5xl text-paper outline-none focus:border-gold"
              placeholder={hintKg ? hintKg.toFixed(1) : "75.0"}
              aria-invalid={value !== "" && !valid}
            />
            {value !== "" && parsed !== 0 && (parsed < 30 || parsed > 300 || !Number.isFinite(parsed)) && (
              <p className="mt-2 text-xs text-coral">Enter a weight between 30 and 300 kg.</p>
            )}
            <label className="eyebrow mt-6 block" htmlFor="log-day">Day</label>
            <input
              id="log-day"
              type="date"
              value={day}
              max={today}
              onChange={(e) => setDay(e.target.value)}
              className="num mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 text-xl text-paper outline-none focus:border-gold"
            />
            {existing && <p className="mt-2 text-xs text-dim">Replaces {existing.weight_kg.toFixed(1)} kg logged for this day.</p>}
            {(save.isError || remove.isError) && (
              <p className="mt-3 text-xs text-coral">{((save.error ?? remove.error) as Error).message || "Couldn't save. Try again."}</p>
            )}
            {save.isSuccess && !save.isPending && value === "" && <p className="mt-3 text-xs text-lime">Saved.</p>}
            <div className="mt-8">
              <button type="submit" className="pop pop-lime" disabled={!valid || save.isPending}>
                {save.isPending ? "Saving…" : "Save weight"}
              </button>
            </div>
          </form>

          {entries.data && entries.data.entries.length > 0 && (
            <div className="mt-10 border-t border-line pt-6">
              <p className="eyebrow mb-3">Your manual entries</p>
              <ul className="divide-y divide-line">
                {entries.data.entries.slice(0, 6).map((e) => (
                  <li key={e.day} className="flex items-center justify-between py-2.5 text-sm">
                    <span className="text-mute">{formatDate(e.day)}</span>
                    <span className="flex items-center gap-4">
                      <span className="num text-paper">{e.weight_kg.toFixed(1)} kg</span>
                      <button
                        type="button"
                        aria-label={`Delete ${e.day}`}
                        className="p-1 text-dim hover:text-coral pointer-coarse:p-2"
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(e.day)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
