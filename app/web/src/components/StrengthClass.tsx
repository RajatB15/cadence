import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ClipboardPaste, Dumbbell, ImageUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import type { ActivityDetail, StrengthBlock, StrengthContent, StrengthLabel } from "../lib/types";

export const PATTERN_LABEL: Record<string, string> = {
  squat: "Squat", hinge: "Hinge", lunge: "Single-leg", push: "Push", pull: "Pull", carry: "Carry", core: "Core", plyometric: "Plyo",
};
const KIND_COLOR: Record<string, string> = {
  warmup: "#5c5a55", cooldown: "#5c5a55", strength: "#ff6a55", conditioning: "#ffbe55", core: "#9b8cff", mixed: "#6cc7ff",
};
const mins = (s: number) => `${Math.round(s / 60)} min`;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Session page: what the class contained, and where each block sits in your heart rate. */
export function ClassContent({ d }: { d: ActivityDetail }) {
  const [editing, setEditing] = useState(false);
  if (!d.strength) return null;
  const label = d.strength.label;
  return (
    <section className="surface p-5 sm:p-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-2">{label ? `${label.summary.exercises} exercises · ${label.blocks.length} blocks` : "Not named yet"}</p>
          <h2 className="font-display text-3xl text-cream">Class content</h2>
        </div>
        {label && !editing && <button type="button" className="pop pop-ghost" onClick={() => setEditing(true)}>Edit</button>}
      </div>
      {label && !editing ? (
        <LabelView label={label} />
      ) : (
        <LabelForm id={d.activity.id} initial={label?.text ?? ""} templates={d.strength.templates} onDone={() => setEditing(false)} canCancel={Boolean(label)} />
      )}
    </section>
  );
}

function LabelView({ label }: { label: StrengthLabel }) {
  const seg = label.segments;
  const total = seg ? seg.segments[seg.segments.length - 1].end_s - seg.segments[0].start_s : 0;
  return (
    <div className="space-y-6">
      {seg && (
        <div>
          <div className="flex h-9 w-full overflow-hidden border border-line">
            {seg.segments.map((s) => (
              <div key={s.name + s.start_s} title={`${s.name} · ${mins(s.end_s - s.start_s)} · avg ${s.avg_hr} bpm`}
                className="flex items-center justify-center overflow-hidden border-r border-ink/60 px-1 text-[10px] font-semibold text-ink uppercase"
                style={{ width: `${((s.end_s - s.start_s) / total) * 100}%`, background: KIND_COLOR[s.kind] ?? "#8d8a82" }}>
                <span className="truncate">{s.name}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {seg.segments.map((s) => (
              <div key={s.name + s.start_s} className="flex items-baseline justify-between gap-3 border-b border-line py-1.5 text-sm">
                <span className="truncate text-paper">{s.name}</span>
                <span className="num shrink-0 text-xs text-mute">{mins(s.end_s - s.start_s)} · {s.avg_hr} avg · {s.max_hr} max{s.hard_pct != null ? ` · ${s.hard_pct}% Z4+` : ""}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-dim">
            Blocks are placed from the shape of your heart rate (fit {Math.round(seg.fit * 100)}%), so boundaries are approximate to a minute or two.
            Your watch doesn't record which exercise was when.
          </p>
        </div>
      )}
      <Blocks blocks={label.blocks} />
      <div className="flex flex-wrap gap-2">
        {Object.entries(label.summary.patterns).map(([p, n]) => (
          <span key={p} className="chip">{PATTERN_LABEL[p] ?? p} × {n}</span>
        ))}
        {label.summary.heavy_lower && <span className="chip text-coral">Heavy lower body</span>}
      </div>
    </div>
  );
}

function Blocks({ blocks }: { blocks: StrengthBlock[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {blocks.map((b, i) => (
        <div key={b.name + i} className="border border-line bg-ink/40 p-4" style={{ borderTop: `3px solid ${KIND_COLOR[b.kind]}` }}>
          <p className="eyebrow mb-1">{b.kind}</p>
          <p className="font-semibold text-paper">{b.name}</p>
          <ul className="mt-2 space-y-1 text-sm">
            {b.exercises.map((e, j) => (
              <li key={e.name + j} className="flex items-baseline justify-between gap-2">
                <span className={clsx("truncate", e.pattern ? "text-mute" : "text-amber")}>{e.name}</span>
                <span className="shrink-0 text-[10px] tracking-widest text-dim uppercase">{e.pattern ? PATTERN_LABEL[e.pattern] : "unknown"}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function LabelForm({ id, initial, templates, onDone, canCancel }: {
  id: number; initial: string; templates: { id: number; name: string; text: string }[]; onDone: () => void; canCancel: boolean;
}) {
  const [text, setText] = useState(initial);
  const [template, setTemplate] = useState("");
  const client = useQueryClient();
  const typed = useDebounced(text, 400);
  const preview = useQuery({ queryKey: ["strength-parse", typed], queryFn: () => api.parseStrength(typed), enabled: typed.trim().length > 3 });
  const save = useMutation({
    mutationFn: () => api.saveStrength(id, text, template.trim() || null),
    onSuccess: () => {
      for (const key of ["activity", "insights", "overview"]) client.invalidateQueries({ queryKey: [key] });
      onDone();
    },
  });
  const box = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const read = useMutation({
    // Several screenshots (a long class list) are read in order and joined.
    mutationFn: async (files: File[]) => {
      const parts = [];
      for (const f of files) parts.push((await api.readScreenshot(f)).text);
      return parts.join("\n");
    },
    onSuccess: (joined) => setText(joined),
  });
  const [pasteError, setPasteError] = useState(false);
  // Safari only exposes clipboard reading on secure (HTTPS) pages: over home Wi-Fi (plain HTTP) it doesn't exist.
  const canRead = typeof window !== "undefined" && window.isSecureContext && Boolean(navigator.clipboard?.readText);
  const paste = async () => {
    try {
      const clip = await navigator.clipboard.readText();
      if (clip.trim()) setText(clip);
      setPasteError(!clip.trim());
    } catch {
      setPasteError(true);
      box.current?.focus();
    }
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-mute">
        Upload the class screenshot: Cadence reads the text on its own machine (nothing goes to a third party), finds the blocks and exercises, and you check them before saving.
        Warm-up and cool-down are added from your heart rate.
      </p>
      <input ref={picker} type="file" accept="image/*" multiple hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) read.mutate(files);
          e.target.value = "";
        }} />
      <button type="button" className="pop pop-lime w-full justify-center sm:w-auto" disabled={read.isPending} onClick={() => picker.current?.click()}>
        <ImageUp size={18} /> {read.isPending ? "Reading screenshot…" : "Upload screenshot"}
      </button>
      {read.isError && <p className="text-sm text-coral">{(read.error as Error).message}</p>}
      <p className="text-xs text-dim">Or paste or type the text below. Several screenshots can be picked at once.</p>
      <div className="flex flex-wrap gap-2">
        {canRead && <button type="button" className="pop pop-ghost" onClick={paste}><ClipboardPaste size={16} /> Paste</button>}
        {templates.map((t) => (
          <button key={t.id} type="button" className="chip pointer-coarse:py-2" onClick={() => setText(t.text)}>{t.name}</button>
        ))}
      </div>
      {pasteError && !text && (
        <p className="text-sm text-gold">Your browser didn't share the clipboard. Tap the box below, then tap again (or hold) and choose <b>Paste</b>.</p>
      )}
      <textarea ref={box} value={text} onChange={(e) => setText(e.target.value)} rows={8} maxLength={4000} aria-label="Class text"
        placeholder={"Tap here, then hold and choose Paste\n\nGet Stronger\nBarbell Front Squats\nGlute Bridges"}
        autoCapitalize="off" autoCorrect="off" spellCheck={false}
        className="w-full border border-line-strong bg-ink/40 p-3 font-mono text-base text-paper outline-none focus:border-gold sm:text-sm" />
      {preview.isError && <p className="text-xs text-coral">Couldn't read the text: {(preview.error as Error).message}</p>}
      {preview.data && preview.data.blocks.length > 0 ? (
        <div>
          <p className="eyebrow mb-2">Preview</p>
          <Blocks blocks={preview.data.blocks} />
          {preview.data.summary.unknown.length > 0 && (
            <p className="mt-2 text-xs text-amber">Not in the exercise list yet: {preview.data.summary.unknown.join(", ")}. They're kept, just without a movement pattern.</p>
          )}
        </div>
      ) : typed.trim().length > 3 && !preview.isFetching ? (
        <p className="text-xs text-dim">No exercises recognised yet. Put each block title on its own line, or start it with #.</p>
      ) : null}
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex-1">
          <span className="eyebrow">Save as a template (optional)</span>
          <input value={template} onChange={(e) => setTemplate(e.target.value)} maxLength={80} placeholder="adidas strength+"
            className="mt-1 w-full border-b-2 border-line-strong bg-transparent py-2 text-paper outline-none focus:border-gold" />
        </label>
        <button type="button" className="pop pop-lime" disabled={!preview.data?.blocks.length || save.isPending} onClick={() => save.mutate()}>Save</button>
        {canCancel && <button type="button" className="pop pop-ghost" onClick={onDone}>Cancel</button>}
      </div>
      {save.isError && <p className="text-xs text-coral">{(save.error as Error).message}</p>}
    </div>
  );
}

/** Coach section: movement patterns from named classes over the last 4 weeks. */
export function StrengthPanel({ s }: { s: StrengthContent | null }) {
  if (!s) return <p className="text-sm text-mute">No strength sessions in the last 4 weeks.</p>;
  const order = ["squat", "hinge", "lunge", "push", "pull", "core", "plyometric", "carry"];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-8">
        <Stat label="Sessions · 28d" value={s.sessions_28d} />
        <Stat label="Named" value={`${s.labelled_28d}/${s.sessions_28d}`} />
        <Stat label="Heavy lower · this week" value={s.heavy_lower_this_week} />
      </div>
      {s.labelled_28d > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {order.map((p) => (
            <div key={p} className="border border-line bg-ink/40 p-4">
              <p className="eyebrow mb-1">{PATTERN_LABEL[p]}</p>
              <p className={clsx("num text-2xl", s.patterns_28d[p] ? "text-cream" : "text-dim")}>{s.patterns_28d[p] ?? 0}</p>
              <p className="text-xs text-dim">{s.last_trained[p] ? `last ${formatDate(s.last_trained[p])}` : "not yet"}</p>
            </div>
          ))}
        </div>
      )}
      {s.unlabelled.length > 0 && (
        <div>
          <p className="eyebrow mb-2">Name these sessions</p>
          <ul className="divide-y divide-line border-y border-line">
            {s.unlabelled.map((a) => (
              <li key={a.id}>
                <Link to={`/activities/${a.id}`} className="flex items-center justify-between gap-3 py-3 text-sm hover:text-paper">
                  <span className="flex items-center gap-2 text-paper"><Dumbbell size={14} className="text-coral" /> {a.name}</span>
                  <span className="text-dim">{formatDate(a.day)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-3xl text-cream">{value}</p>
    </div>
  );
}
