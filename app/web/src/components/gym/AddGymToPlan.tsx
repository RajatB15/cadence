import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import type { GymImportResult, GymSetting } from "../../lib/types";
import { Segmented } from "../Shell";
import { useGymSessions, useGymSettings } from "./useGym";

const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;

/** Add a gym session to a day, two ways: from screenshots (read, matched to the exercise library, reviewed) or one of your saved sessions. */
export function AddGymToPlan({ day, today }: { day: string; today: string }) {
  const [how, setHow] = useState<"screenshot" | "saved">("screenshot");
  const [hour, setHour] = useState<number | null>(null);
  const [added, setAdded] = useState<{ planId: number; title: string } | null>(null);
  const client = useQueryClient();
  const done = (planId: number, title: string) => {
    setAdded({ planId, title });
    ["planner", "overview", "insights"].forEach((k) => client.invalidateQueries({ queryKey: [k] }));
    client.invalidateQueries({ queryKey: ["gym"] });
  };
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <Segmented label="How" options={[{ value: "screenshot" as const, label: "From screenshots" }, { value: "saved" as const, label: "My gym sessions" }]} value={how} onChange={(v) => { setHow(v); setAdded(null); }} />
        <label className="block">
          <span className="eyebrow">Start time</span>
          <select value={hour ?? ""} onChange={(e) => setHour(e.target.value === "" ? null : Number(e.target.value))}
            className="mt-2 block border-b-2 border-line-strong bg-coal py-2 text-base text-paper outline-none focus:border-gold">
            <option value="">Usual time</option>
            {Array.from({ length: 17 }, (_, i) => i + 5).map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
          </select>
        </label>
      </div>
      {added && (
        <p role="status" className="border-l-2 border-lime/60 pl-3 text-sm text-lime">
          “{added.title}” is on {day === today ? "today" : formatDate(day)}. <Link to={`/workout/${added.planId}`} className="underline">Open the plan</Link> to see every step and start it.
        </p>
      )}
      {how === "screenshot" ? <FromScreenshots day={day} today={today} hour={hour} onAdded={done} /> : <FromSaved day={day} today={today} hour={hour} onAdded={done} />}
    </div>
  );
}

function FromScreenshots({ day, today, hour, onAdded }: { day: string; today: string; hour: number | null; onAdded: (planId: number, title: string) => void }) {
  const picker = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const settings = useGymSettings();
  const [text, setText] = useState("");
  const [draft, setDraft] = useState<GymImportResult | null>(null);
  const [name, setName] = useState("");
  const [setting, setSetting] = useState<GymSetting | null>(null);
  const where = setting ?? settings.data?.default_setting ?? "gym";
  const read = useMutation({
    mutationFn: async (files: File[]) => {
      const parts: string[] = [];
      for (const f of files) parts.push((await api.readScreenshot(f)).text);
      return parts.join("\n");
    },
    onSuccess: (t) => { setText((old) => (old.trim() ? `${old.trim()}\n${t}` : t)); setDraft(null); },
  });
  const make = useMutation({
    mutationFn: () => api.gymImport(text),
    onSuccess: (r) => { setDraft(r); setName(r.name); },
  });
  const create = async () => {
    const d = draft!;
    return api.gymCreate({ name: name.trim() || d.name, setting: where, format: d.format, steps: d.steps, notes: d.ignored.length ? `Not used from the screenshot: ${d.ignored.join("; ")}` : null });
  };
  const add = useMutation({
    mutationFn: async () => {
      const s = await create();
      const p = await api.gymSchedule(s.id, { day, start_hour: hour });
      return { id: p.id, title: s.name };
    },
    onSuccess: (r) => { onAdded(r.id, r.title); setDraft(null); setText(""); },
  });
  const review = useMutation({
    mutationFn: create,
    onSuccess: (s) => { void client_invalidate(); navigate(`/gym?session=${s.id}`); },
  });
  const client = useQueryClient();
  const client_invalidate = () => client.invalidateQueries({ queryKey: ["gym"] });
  return (
    <div className="space-y-4">
      <p className="text-sm text-mute">Upload one or more screenshots of a class, a coach’s plan or a workout. Cadence reads the text on this machine, finds the exercises and sets, and builds a session you can check, change and then do set by set.</p>
      <input ref={picker} type="file" accept="image/*" multiple hidden onChange={(e) => {
        const files = Array.from(e.target.files ?? []);
        if (files.length) read.mutate(files);
        e.target.value = "";
      }} />
      <button type="button" className="pop pop-lime w-full justify-center !py-3 sm:w-auto" disabled={read.isPending} onClick={() => picker.current?.click()}>
        <ImageUp size={18} /> {read.isPending ? "Reading screenshots…" : text ? "Add more screenshots" : "Upload screenshots"}
      </button>
      {read.isError && <p role="alert" className="text-sm text-coral">{(read.error as Error).message}</p>}
      <textarea value={text} onChange={(e) => { setText(e.target.value); setDraft(null); }} rows={6} aria-label="Workout text"
        placeholder={"…or type or paste it: block titles on their own lines, one exercise per line, e.g.\nMain\nGoblet Squat 4x8 @ 16 kg\nPlank 45 sec\nRun 400 m"}
        className="w-full border border-line-strong bg-ink/40 p-3 font-mono text-base text-paper outline-none focus:border-gold sm:text-sm" />
      <button type="button" className="pop !py-3" disabled={make.isPending || text.trim().length < 3} onClick={() => make.mutate()}>{make.isPending ? "Reading it…" : "Make a session from this"}</button>
      {make.isError && <p role="alert" className="text-sm text-coral">{(make.error as Error).message}</p>}
      {draft && (
        <div className="surface space-y-4 p-4 sm:p-6">
          <p className="eyebrow">Check it</p>
          <label className="block">
            <span className="eyebrow">Name</span>
            <input className="mt-2 w-full border-b-2 border-line-strong bg-transparent py-2 font-display text-2xl text-cream outline-none focus:border-gold" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Segmented label="Where" options={[{ value: "gym" as GymSetting, label: "Full gym" }, { value: "home" as GymSetting, label: "Home" }]} value={where} onChange={setSetting} />
            <span className="num text-sm text-mute">≈ {draft.minutes} min · {draft.total} exercise{draft.total === 1 ? "" : "s"}</span>
          </div>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-white/[0.02] p-3 text-sm text-paper">{draft.outline}</pre>
          <p className="text-xs text-dim">{draft.matched} matched the exercise library (so they have a how-to and can be swapped){draft.unmatched.length > 0 ? `; ${draft.unmatched.length} kept as your own: ${draft.unmatched.join(", ")}` : ""}. Sets and reps are read from the text where it gave them, otherwise a usual 3 × 10.</p>
          {draft.ignored.length > 0 && <p className="text-xs text-mute">Lines that weren’t used: {draft.ignored.join(" · ")}. Add them by hand in the editor if they matter.</p>}
          <div className="flex flex-wrap gap-3">
            <button type="button" className="pop pop-lime !py-3" disabled={add.isPending || review.isPending || !name.trim()} onClick={() => add.mutate()}>{add.isPending ? "Adding…" : `Add to ${day === today ? "today" : formatDate(day)}`}</button>
            <button type="button" className="pop pop-ghost !py-3" disabled={add.isPending || review.isPending || !name.trim()} onClick={() => review.mutate()}>{review.isPending ? "Opening…" : "Review and edit first"}</button>
          </div>
          {(add.isError || review.isError) && <p role="alert" className="text-sm text-coral">{((add.error ?? review.error) as Error).message || "Couldn’t save that."}</p>}
        </div>
      )}
    </div>
  );
}

function FromSaved({ day, today, hour, onAdded }: { day: string; today: string; hour: number | null; onAdded: (planId: number, title: string) => void }) {
  const sessions = useGymSessions();
  const add = useMutation({
    mutationFn: async (s: { id: number; name: string }) => {
      const p = await api.gymSchedule(s.id, { day, start_hour: hour });
      return { id: p.id, title: s.name };
    },
    onSuccess: (r) => onAdded(r.id, r.title),
  });
  const planned = useQuery({ queryKey: ["planner"], queryFn: api.plannerWeek, staleTime: 30_000 });
  void planned;
  if (sessions.isPending) return <div className="h-32 animate-pulse rounded-2xl bg-white/5" aria-busy="true" />;
  if (sessions.isError) return <p role="alert" className="text-sm text-coral">Couldn’t load your sessions. <button type="button" className="underline" onClick={() => sessions.refetch()}>Retry</button></p>;
  if (sessions.data.sessions.length === 0) {
    return <p className="text-sm text-mute">No saved gym sessions yet. <Link to="/gym" className="text-gold underline">Build one</Link>, or make one from screenshots here.</p>;
  }
  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {sessions.data.sessions.map((s) => {
          const here = s.planned?.find((p) => p.day === day);
          const other = (s.planned ?? []).filter((p) => p.day >= today && p.day !== day).slice(0, 2);
          return (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-white/[0.02] px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-paper">{s.name}</p>
                <p className="num text-sm text-mute">≈ {s.minutes} min · {s.exercises} exercises · {s.setting === "home" ? "home" : "gym"}</p>
                {(here || other.length > 0) && <p className="text-xs text-dim">{here ? `Already on ${day === today ? "today" : formatDate(day)}` : `Planned ${other.map((p) => formatDate(p.day)).join(", ")}`}</p>}
              </div>
              <button type="button" className="pop pop-lime !py-3 text-sm" disabled={add.isPending} onClick={() => add.mutate({ id: s.id, name: s.name })}>{here ? "Add again" : `Add to ${day === today ? "today" : formatDate(day)}`}</button>
            </li>
          );
        })}
      </ul>
      {add.isError && <p role="alert" className="text-sm text-coral">{(add.error as Error).message || "Couldn’t add it."}</p>}
      <p className="text-xs text-dim">Or <Link to="/gym" className="text-gold underline">build a new session</Link>. Each one goes on the plan as a copy, so editing it later doesn’t change days already planned (you can update a copy from the editor).</p>
    </div>
  );
}
