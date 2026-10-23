import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Check, ChevronLeft, ChevronRight, Minus, NotebookPen, Plus } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { Behaviour, HabitEffect, HabitProgress } from "../lib/types";
import { Sheet } from "./Sheet";

const shiftDay = (day: string, by: number) => {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + by);
  return d.toISOString().slice(0, 10);
};

function useInvalidateJournal() {
  const client = useQueryClient();
  return () => {
    for (const key of ["journal", "overview", "insights"]) client.invalidateQueries({ queryKey: [key] });
  };
}

/** Home card: yesterday's check-in, offered until it's done. */
export function CheckInCard({ day, done, count, autoOpen }: { day: string; done: boolean; count: number; autoOpen?: boolean }) {
  const [open, setOpen] = useState(Boolean(autoOpen) && !done);
  if (count === 0) return null;
  return (
    <>
      {done ? (
        <button type="button" onClick={() => setOpen(true)} className="chip text-mute hover:text-paper pointer-coarse:py-2">
          <Check size={12} className="text-lime" /> Journal logged for {formatDate(day)} · edit
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="surface surface-hover flex w-full items-center gap-4 p-5 text-left"
          style={{ borderLeft: "3px solid var(--color-violet)" }}
        >
          <NotebookPen size={20} className="shrink-0 text-violet" />
          <div className="min-w-0 flex-1">
            <p className="eyebrow mb-0.5">Morning check-in</p>
            <p className="text-paper">How was yesterday? {count} quick questions.</p>
          </div>
          <ChevronRight size={16} className="shrink-0 text-dim" />
        </button>
      )}
      <JournalSheet open={open} onOpenChange={setOpen} initialDay={day} />
    </>
  );
}

/** Log any of the last 60 days; the default is yesterday. */
export function JournalSheet({ open, onOpenChange, initialDay }: { open: boolean; onOpenChange: (o: boolean) => void; initialDay?: string }) {
  const query = useQuery({ queryKey: ["journal"], queryFn: () => api.journal(60), enabled: open });
  const yesterday = query.data ? shiftDay(query.data.today, -1) : initialDay;
  const [day, setDay] = useState<string | undefined>(initialDay);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [manage, setManage] = useState(false);
  const invalidate = useInvalidateJournal();
  const current = day ?? yesterday;
  const behaviours = (query.data?.behaviours ?? []).filter((b) => b.active);

  useEffect(() => {
    if (!query.data || !current) return;
    setAnswers(query.data.days.find((d) => d.day === current)?.answers ?? {});
  }, [query.data, current]);
  useEffect(() => {
    if (open) {
      setDay(initialDay);
      setManage(false);
    }
  }, [open, initialDay]);

  const save = useMutation({
    mutationFn: () => api.saveJournal(current!, answers),
    onSuccess: () => {
      invalidate();
      onOpenChange(false);
    },
  });
  const logged = query.data?.days.some((d) => d.day === current);
  const oldest = query.data ? shiftDay(query.data.today, -60) : "";

  return (
    <Sheet open={open} onOpenChange={onOpenChange} title={manage ? "Your habits" : "Journal"} eyebrow={manage ? "Choose what to track" : current ? `About ${formatDate(current)}` : undefined}>
      {manage ? (
        <ManageHabits behaviours={query.data?.behaviours ?? []} onDone={() => setManage(false)} />
      ) : !query.data || !current ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : (
        <div className="space-y-6">
          <div className="flex items-center justify-between gap-3">
            <button type="button" aria-label="Previous day" disabled={current <= oldest} onClick={() => setDay(shiftDay(current, -1))}
              className="grid h-10 w-10 place-items-center border border-line-strong text-mute hover:text-paper disabled:opacity-30">
              <ChevronLeft size={18} />
            </button>
            <p className="text-center text-sm text-mute">
              {current === yesterday ? "Yesterday" : formatDate(current)}
              {logged && <span className="ml-2 text-lime">· logged</span>}
            </p>
            <button type="button" aria-label="Next day" disabled={!yesterday || current >= yesterday} onClick={() => setDay(shiftDay(current, 1))}
              className="grid h-10 w-10 place-items-center border border-line-strong text-mute hover:text-paper disabled:opacity-30">
              <ChevronRight size={18} />
            </button>
          </div>
          <ul className="divide-y divide-line border-y border-line">
            {behaviours.map((b) => (
              <li key={b.key} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-paper">{b.label}</p>
                  <p className="text-xs text-dim">{b.question}</p>
                </div>
                {b.kind === "count" ? (
                  <Stepper value={answers[b.key] ?? 0} unit={b.unit} onChange={(v) => setAnswers((a) => ({ ...a, [b.key]: v }))} />
                ) : (
                  <YesNo value={answers[b.key] ?? 0} onChange={(v) => setAnswers((a) => ({ ...a, [b.key]: v }))} />
                )}
              </li>
            ))}
          </ul>
          <p className="text-xs text-dim">Anything you leave as "No" is saved as no: a no is as useful to the statistics as a yes.</p>
          {save.isError && <p className="text-xs text-coral">{(save.error as Error).message}</p>}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <button type="button" className="pop pop-lime" disabled={save.isPending} onClick={() => save.mutate()}>
              {logged ? "Update" : "Save"}
            </button>
            <button type="button" className="eyebrow hover:text-paper pointer-coarse:py-3" onClick={() => setManage(true)}>
              Edit habits
            </button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

function YesNo({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div role="radiogroup" className="flex shrink-0 border border-line-strong p-0.5">
      {[0, 1].map((v) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={clsx("min-w-12 px-3 py-2 text-xs font-semibold tracking-widest uppercase",
            value === v ? (v ? "bg-violet text-ink" : "bg-slate text-paper") : "text-dim")}>
          {v ? "Yes" : "No"}
        </button>
      ))}
    </div>
  );
}

function Stepper({ value, unit, onChange }: { value: number; unit: string; onChange: (v: number) => void }) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <button type="button" aria-label="Less" disabled={value <= 0} onClick={() => onChange(value - 1)}
        className="grid h-10 w-10 place-items-center border border-line-strong text-mute disabled:opacity-30">
        <Minus size={14} />
      </button>
      <span className={clsx("num w-14 text-center", value ? "text-violet" : "text-dim")}>
        {value}
        <span className="block text-[10px] text-dim">{unit}</span>
      </span>
      <button type="button" aria-label="More" disabled={value >= 30} onClick={() => onChange(value + 1)}
        className="grid h-10 w-10 place-items-center border border-line-strong text-mute disabled:opacity-30">
        <Plus size={14} />
      </button>
    </div>
  );
}

function ManageHabits({ behaviours, onDone }: { behaviours: Behaviour[]; onDone: () => void }) {
  const invalidate = useInvalidateJournal();
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<Behaviour["kind"]>("yes_no");
  const toggle = useMutation({ mutationFn: (b: Behaviour) => api.updateBehaviour(b.key, { active: !b.active }), onSuccess: invalidate });
  const add = useMutation({
    mutationFn: () => api.addBehaviour({ label: label.trim(), question: "", kind, unit: kind === "count" ? "times" : "" }),
    onSuccess: () => {
      setLabel("");
      invalidate();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (label.trim()) add.mutate();
  };
  return (
    <div className="space-y-6">
      <ul className="divide-y divide-line border-y border-line">
        {behaviours.map((b) => (
          <li key={b.key} className="flex items-center justify-between gap-4 py-3">
            <div className="min-w-0">
              <p className={b.active ? "text-paper" : "text-dim line-through"}>{b.label}</p>
              <p className="text-xs text-dim">{b.question}</p>
            </div>
            <button type="button" onClick={() => toggle.mutate(b)} disabled={toggle.isPending}
              className={clsx("chip shrink-0 pointer-coarse:py-2", b.active ? "text-lime" : "text-dim")}>
              {b.active ? "Tracking" : "Off"}
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="space-y-3">
        <label htmlFor="new-habit" className="eyebrow">Add your own</label>
        <input id="new-habit" value={label} maxLength={60} onChange={(e) => setLabel(e.target.value)} placeholder="Cold plunge"
          className="w-full border-b-2 border-line-strong bg-transparent py-2 text-xl text-paper outline-none focus:border-gold" />
        <div className="flex flex-wrap items-center gap-3">
          <YesNoKind value={kind} onChange={setKind} />
          <button type="submit" className="pop" disabled={!label.trim() || add.isPending}>Add</button>
        </div>
        {add.isError && <p className="text-xs text-coral">{(add.error as Error).message}</p>}
      </form>
      <button type="button" className="pop pop-ghost" onClick={onDone}>Back to the check-in</button>
    </div>
  );
}

function YesNoKind({ value, onChange }: { value: Behaviour["kind"]; onChange: (k: Behaviour["kind"]) => void }) {
  return (
    <div role="radiogroup" aria-label="Answer type" className="flex border border-line-strong p-0.5">
      {(["yes_no", "count"] as const).map((k) => (
        <button key={k} type="button" role="radio" aria-checked={value === k} onClick={() => onChange(k)}
          className={clsx("px-3 py-2 text-xs font-semibold tracking-widest uppercase", value === k ? "bg-cream text-ink" : "text-dim")}>
          {k === "yes_no" ? "Yes / no" : "Count"}
        </button>
      ))}
    </div>
  );
}

/** Coach section: what each habit does to your recovery, and how close the rest are to an answer. */
export function HabitsPanel({ effects, progress }: { effects: HabitEffect[]; progress: HabitProgress[] }) {
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  const clear = effects.filter((e) => e.significant);
  const shown = all ? effects : clear;
  const waiting = progress.filter((p) => !p.ready);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-mute">
          Each habit is compared with the next night's sleep, next morning's HRV, resting HR and readiness, and next-day run efficiency,
          allowing for training load and weekends. A habit is tested once it has {progress[0]?.needed ?? 8} days each way.
        </p>
        <button type="button" className="pop" onClick={() => setOpen(true)}>
          <NotebookPen size={16} /> Log a day
        </button>
      </div>
      {shown.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((e) => {
            const bad = e.higher_is_better ? e.diff < 0 : e.diff > 0;
            const color = !e.significant ? "#8d8a82" : bad ? "#ff6a55" : "#c8f560";
            return (
              <motion.div key={e.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="border border-line bg-ink/40 p-5">
                <p className="eyebrow mb-2">{e.cause} → {e.outcome}</p>
                <p className="text-paper">{e.exposed} <span className="text-mute">vs {e.reference.toLowerCase()}</span></p>
                <p className="num mt-3 text-3xl" style={{ color }}>
                  {e.diff > 0 ? "+" : ""}{e.diff.toFixed(1)}<span className="ml-1 text-sm text-mute">{e.unit || "pts"}</span>
                </p>
                <p className="text-xs text-dim">
                  {e.exposed_mean.toFixed(1)} vs {e.reference_mean.toFixed(1)} · n = {e.n_exposed} / {e.n_reference} ·{" "}
                  {e.significant ? `clear (q = ${e.q_value.toFixed(3)})` : `could be noise (q = ${e.q_value.toFixed(2)})`}
                </p>
              </motion.div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-mute">{effects.length ? "No clear effects yet." : "No habit has enough days logged yet."}</p>
      )}
      {effects.length > clear.length && (
        <button type="button" onClick={() => setAll((a) => !a)} className="eyebrow hover:text-paper pointer-coarse:py-3">
          {all ? "Only clear effects" : `Show all ${effects.length} tested`}
        </button>
      )}
      {waiting.length > 0 && (
        <div>
          <p className="eyebrow mb-3">Still collecting</p>
          <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {waiting.map((p) => (
              <div key={p.key}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate text-paper">{p.label}</span>
                  <span className="num shrink-0 text-xs text-dim" title={`${p.yes_label} vs ${p.no_label.toLowerCase()}`}>
                    {Math.min(p.yes, p.needed)}/{p.needed} yes · {Math.min(p.no, p.needed)}/{p.needed} no
                  </span>
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-1">
                  {[p.yes, p.no].map((n, i) => (
                    <div key={i} className="h-1 bg-line-strong">
                      <div className="h-full" style={{ width: `${Math.min(1, n / p.needed) * 100}%`, background: i ? "#8d8a82" : "#9b8cff" }} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <JournalSheet open={open} onOpenChange={setOpen} />
    </div>
  );
}
