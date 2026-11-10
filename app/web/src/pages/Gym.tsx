import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Dumbbell, Home, Plus, Search, Shuffle } from "lucide-react";
import { useDeferredValue, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ExerciseGuide } from "../components/gym/ExerciseGuide";
import { SessionEditor } from "../components/gym/SessionEditor";
import { EQUIPMENT_LABEL, LEVEL_LABEL, PATTERN_LABEL, useGymSessions, useGymSettings, useGymTemplates } from "../components/gym/useGym";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { api } from "../lib/api";
import type { GymDraft, GymSession, GymSetting } from "../lib/types";

type Tab = "sessions" | "build" | "exercises";

const blank = (setting: GymSetting): GymDraft => ({ name: "", setting, format: "custom", steps: [], notes: null });
const fromSession = (s: GymSession): GymDraft => ({ id: s.id, name: s.name, setting: s.setting, format: s.format, steps: s.steps, notes: s.notes });

export function GymPage() {
  const client = useQueryClient();
  const sessions = useGymSessions();
  const settings = useGymSettings();
  const [tab, setTab] = useState<Tab>("sessions");
  const [draft, setDraft] = useState<GymDraft | null>(null);
  const [planned, setPlanned] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: ["gym", "sessions"] });
  // /gym?session=ID opens that session in the editor (the plan view links here).
  const [params, setParams] = useSearchParams();
  const wanted = Number(params.get("session"));
  useEffect(() => {
    if (!wanted || !sessions.data) return;
    const s = sessions.data.sessions.find((x) => x.id === wanted);
    if (s) setDraft(fromSession(s));
    setParams({}, { replace: true });
  }, [wanted, sessions.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: (d: GymDraft) => (d.id ? api.gymUpdate(d.id, { name: d.name.trim(), setting: d.setting, format: d.format, steps: d.steps, notes: d.notes }) : api.gymCreate({ name: d.name.trim(), setting: d.setting, format: d.format, steps: d.steps, notes: d.notes })),
    onSuccess: (s) => { setDraft(fromSession(s)); setFailed(null); refresh(); },
    onError: (e: Error) => setFailed(e.message || "Couldn’t save that."),
  });
  const plan = useMutation({
    mutationFn: async ({ d, day, hour }: { d: GymDraft; day: string; hour: number | null }) => {
      const saved = await save.mutateAsync(d);
      return api.gymSchedule(saved.id, { day, start_hour: hour });
    },
    onSuccess: (p) => { setPlanned(p.day); client.invalidateQueries({ queryKey: ["planner"] }); client.invalidateQueries({ queryKey: ["insights"] }); },
    onError: (e: Error) => setFailed(e.message || "Couldn’t add it to the plan."),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.gymDelete(id),
    onSuccess: () => { setDraft(null); setAsking(false); refresh(); },
  });

  const open = (d: GymDraft) => { setDraft(d); setPlanned(null); setFailed(null); window.scrollTo({ top: 0 }); };
  const count = sessions.data?.sessions.length ?? 0;

  return (
    <>
      <PageHeader eyebrow={<>{count} saved session{count === 1 ? "" : "s"}<Link to="/plan" className="text-dim hover:text-paper">Plan</Link></>} title={<>Gym <em className="text-gold">sessions.</em></>} />
      {draft ? (
        <>
          <button type="button" className="mb-6 text-sm text-mute hover:text-paper" onClick={() => setDraft(null)}>← Back</button>
          <SessionEditor draft={draft} onChange={setDraft} saving={save.isPending} saveLabel={draft.id ? "Save changes" : "Save session"} planning={plan.isPending}
            planned={planned} error={failed} onSave={() => save.mutate(draft)} onPlan={(day, hour) => plan.mutate({ d: draft, day, hour })}
            onDelete={draft.id ? () => setAsking(true) : undefined} />
          <ConfirmDialog open={asking} title="Delete this session?" body="Copies already put on the plan stay there." confirmLabel="Delete" onCancel={() => setAsking(false)} onConfirm={() => draft.id && remove.mutate(draft.id)} />
        </>
      ) : (
        <>
          <div className="mb-8 flex flex-wrap gap-2" role="tablist" aria-label="Gym">
            {([["sessions", "My sessions"], ["build", "Build"], ["exercises", "Exercises"]] as const).map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={clsx("chip pointer-coarse:py-2", tab === k ? "border-gold text-cream" : "text-mute hover:text-paper")}>{label}</button>
            ))}
          </div>
          {tab === "sessions" && <SessionList q={sessions} onOpen={(s) => open(fromSession(s))} onBuild={() => setTab("build")} />}
          {tab === "build" && <Build defaultSetting={settings.data?.default_setting ?? "gym"} onDraft={open} />}
          {tab === "exercises" && <Exercises />}
        </>
      )}
    </>
  );
}

function SessionList({ q, onOpen, onBuild }: { q: ReturnType<typeof useGymSessions>; onOpen: (s: GymSession) => void; onBuild: () => void }) {
  if (q.isPending) return <LoadingBlock height={240} />;
  if (q.isError) return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  if (q.data.sessions.length === 0) {
    return (
      <div className="surface p-12 text-center text-mute">
        <Dumbbell className="mx-auto mb-4 text-gold" size={28} aria-hidden />
        <p>No sessions yet. Build one from a template, or start from scratch.</p>
        <button type="button" className="pop mt-6" onClick={onBuild}>Build a session</button>
      </div>
    );
  }
  return (
    <ul className="stagger grid gap-4 md:grid-cols-2">
      {q.data.sessions.map((s) => (
        <li key={s.id}>
          <button type="button" onClick={() => onOpen(s)} className="surface surface-hover block h-full w-full space-y-3 p-5 text-left">
            <p className="eyebrow flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="flex items-center gap-1">{s.setting === "home" ? <Home size={12} /> : <Dumbbell size={12} />}{s.setting === "home" ? "Home" : "Gym"}</span>
              <span>{s.format}</span><span className="text-dim">≈ {s.minutes} min</span>
            </p>
            <h2 className="font-display text-2xl leading-tight text-cream">{s.name}</h2>
            <p className="text-sm text-mute">{s.exercises} exercises · {s.patterns.map((p) => PATTERN_LABEL[p] ?? p).join(", ")}</p>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Build({ defaultSetting, onDraft }: { defaultSetting: GymSetting; onDraft: (d: GymDraft) => void }) {
  const templates = useGymTemplates();
  const [template, setTemplate] = useState("full_body");
  const [setting, setSetting] = useState<GymSetting>(defaultSetting);
  const [level, setLevel] = useState("intermediate");
  const [goal, setGoal] = useState("general");
  const [minutes, setMinutes] = useState(45);
  const [seed, setSeed] = useState(1);
  const [notes, setNotes] = useState<string[]>([]);
  const gen = useMutation({
    mutationFn: (s: number) => api.gymGenerate({ template, setting, minutes, level, goal, seed: s }),
    onSuccess: (r, s) => { setSeed(s); setNotes(r.notes); onDraft({ name: r.name, setting: r.setting, format: r.format, steps: r.steps, notes: r.notes.length ? r.notes.join("\n") : null }); },
  });
  if (templates.isPending) return <LoadingBlock height={240} />;
  if (templates.isError) return <ErrorBlock error={templates.error} retry={() => templates.refetch()} />;
  const hyrox = template.startsWith("hyrox");
  return (
    <div className="space-y-8">
      <section>
        <p className="eyebrow mb-3">Template</p>
        <ul className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {templates.data.templates.map((t) => (
            <li key={t.id}>
              <button type="button" aria-pressed={template === t.id} onClick={() => setTemplate(t.id)} className={clsx("surface surface-hover h-full w-full space-y-1 p-4 text-left", template === t.id && "!border-gold")}>
                <span className="block font-display text-xl text-cream">{t.name}</span>
                <span className="block text-sm text-mute">{t.blurb}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section className="surface space-y-6 p-5 sm:p-8">
        <div className="flex flex-wrap gap-x-10 gap-y-5">
          <div><p className="eyebrow mb-2">Where</p><Segmented label="Where" options={[{ value: "gym" as GymSetting, label: "Full gym" }, { value: "home" as GymSetting, label: "Home" }]} value={setting} onChange={setSetting} /></div>
          {!hyrox && <div><p className="eyebrow mb-2">Level</p><Segmented label="Level" options={templates.data.levels.map((l) => ({ value: l, label: l[0].toUpperCase() + l.slice(1) }))} value={level} onChange={setLevel} /></div>}
          {!hyrox && template !== "run_lift" && <div><p className="eyebrow mb-2">Focus</p><Segmented label="Focus" options={templates.data.goals.map((g) => ({ value: g, label: g[0].toUpperCase() + g.slice(1) }))} value={goal} onChange={setGoal} /></div>}
        </div>
        {!hyrox && (
          <label className="block max-w-sm">
            <span className="eyebrow">Time · <span className="num text-paper">{minutes} min</span></span>
            <input type="range" min={20} max={90} step={5} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="mt-3 w-full accent-[var(--color-gold)]" aria-label="Minutes" />
          </label>
        )}
        {hyrox && <p className="max-w-2xl text-sm text-mute">Eight rounds of a 1 km run then a station, in race order. Station loads are left blank: set them from the current official rulebook for your division. At home, the stations that need a sled, rower or SkiErg are swapped for the closest bodyweight work.</p>}
        {setting === "home" && <HomeEquipment />}
        <div className="flex flex-wrap gap-3">
          <button type="button" className="pop pop-lime" disabled={gen.isPending} onClick={() => gen.mutate(seed)}>{gen.isPending ? "Building…" : "Build it"}</button>
          <button type="button" className="pop pop-ghost" disabled={gen.isPending} onClick={() => gen.mutate(seed + 1)} title="A different mix of exercises"><Shuffle size={14} /> Shuffle</button>
          <button type="button" className="pop pop-ghost" onClick={() => onDraft(blank(setting))}><Plus size={14} /> Start from scratch</button>
        </div>
        {gen.isError && <p role="alert" className="text-sm text-coral">{(gen.error as Error).message || "Couldn’t build that."}</p>}
        {notes.length > 0 && <ul className="text-xs text-dim">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        <p className="text-xs text-dim">Sessions are built by simple rules from the exercise library: no model, no load advice. Loads are yours to set.</p>
      </section>
    </div>
  );
}

function HomeEquipment() {
  const client = useQueryClient();
  const q = useGymSettings();
  const save = useMutation({ mutationFn: api.setGymSettings, onSuccess: (s) => client.setQueryData(["gym", "settings"], s) });
  if (!q.data) return null;
  const have = new Set(q.data.home_equipment);
  const toggle = (e: string) => save.mutate({ home_equipment: [...(have.has(e) ? [...have].filter((x) => x !== e) : [...have, e])] });
  return (
    <div>
      <p className="eyebrow mb-2">What you have at home</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Home equipment">
        {q.data.equipment.filter((e) => ["dumbbell", "kettlebell", "barbell", "bench", "rack", "pullup_bar", "band", "box", "medicine_ball", "sandbag", "rings", "bike", "treadmill", "rower", "skierg", "sled"].includes(e)).map((e) => (
          <button key={e} type="button" aria-pressed={have.has(e)} disabled={save.isPending} onClick={() => toggle(e)} className={clsx("chip pointer-coarse:py-2", have.has(e) ? "border-gold text-cream" : "text-mute")}>{EQUIPMENT_LABEL[e] ?? e}</button>
        ))}
      </div>
      <p className="mt-2 text-xs text-dim">Bodyweight is always available. With nothing ticked, home sessions use only your body, a wall and a chair.</p>
      {save.isError && <p role="alert" className="mt-2 text-sm text-coral">Couldn’t save that.</p>}
    </div>
  );
}

function Exercises() {
  const [q, setQ] = useState("");
  const [pattern, setPattern] = useState<string | null>(null);
  const [setting, setSetting] = useState<GymSetting | "all">("all");
  const [guide, setGuide] = useState<string | null>(null);
  const deferred = useDeferredValue(q);
  const query = useQuery({ queryKey: ["gym", "browse", deferred, pattern, setting], queryFn: () => api.gymLibrary({ q: deferred, pattern: pattern ?? undefined, setting: setting === "all" ? undefined : setting, limit: 200 }), staleTime: 60_000 });
  return (
    <div className="space-y-5">
      <label className="flex items-center gap-2 border-b-2 border-line-strong focus-within:border-gold">
        <Search size={16} className="text-dim" aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the library: squat, hyrox, band…" aria-label="Search exercises" className="w-full bg-transparent py-3 text-lg text-paper outline-none" />
      </label>
      <div className="flex flex-wrap items-center gap-4">
        <Segmented label="Setting" options={[{ value: "all" as const, label: "All" }, { value: "gym" as const, label: "Gym" }, { value: "home" as const, label: "Home" }]} value={setting} onChange={setSetting} />
        <span className="num text-sm text-dim">{query.data ? `${query.data.count} of ${query.data.total}` : ""}</span>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Movement">
        <button type="button" aria-pressed={pattern == null} className={clsx("chip pointer-coarse:py-2", pattern == null ? "border-gold text-cream" : "text-mute")} onClick={() => setPattern(null)}>All</button>
        {(query.data?.patterns ?? Object.keys(PATTERN_LABEL)).map((p) => (
          <button key={p} type="button" aria-pressed={pattern === p} className={clsx("chip pointer-coarse:py-2", pattern === p ? "border-gold text-cream" : "text-mute")} onClick={() => setPattern(p)}>{PATTERN_LABEL[p] ?? p}</button>
        ))}
      </div>
      {query.isPending ? <LoadingBlock height={200} /> : query.isError ? <ErrorBlock error={query.error} retry={() => query.refetch()} /> : query.data.exercises.length === 0 ? (
        <div className="surface p-10 text-center text-mute">Nothing matches. Try another word, movement or setting.</div>
      ) : (
        <ul className="stagger grid gap-3 md:grid-cols-2">
          {query.data.exercises.map((e) => (
            <li key={e.id}>
              <button type="button" onClick={() => setGuide(e.id)} className="surface surface-hover block h-full w-full space-y-1 p-4 text-left">
                <span className="block text-paper">{e.name}</span>
                <span className="block text-xs text-dim">{PATTERN_LABEL[e.pattern]} · {LEVEL_LABEL[e.level]} · {e.needs}</span>
                <span className="block truncate text-xs text-mute">{e.muscles.primary.join(", ")}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <ExerciseGuide id={guide} onClose={() => setGuide(null)} />
    </div>
  );
}
