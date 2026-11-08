import { edge } from "../lib/color";
import { clsx } from "clsx";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Flame, Info } from "lucide-react";
import { motion } from "motion/react";
import { Link, useLocation } from "react-router-dom";
import type { Finding, Verdict } from "../lib/types";
import { CountUp } from "./CountUp";
import { C } from "../lib/theme";

export const SEVERITY: Record<Finding["severity"], { color: string; icon: typeof Info; label: string }> = {
  alert: { color: C.coral, icon: AlertTriangle, label: "Act now" },
  warn: { color: C.amber, icon: AlertTriangle, label: "Fix this" },
  info: { color: C.sky, icon: Info, label: "Worth knowing" },
  good: { color: C.lime, icon: CheckCircle2, label: "Working" },
};

export const readyColor = (s: number) => (s >= 85 ? C.lime : s >= 70 ? C.mint : s >= 50 ? C.amber : C.coral);

const VERDICT_COLOR: Record<Verdict["tone"], string> = {
  good: C.lime,
  warn: C.amber,
  info: C.sky,
  key: C.gold,
};

export function VerdictChip({ v, large = false }: { v: Verdict; large?: boolean }) {
  const color = VERDICT_COLOR[v.tone];
  return (
    <span
      className={clsx("chip shrink-0 gap-1", large && "!px-3 !py-1.5 !text-xs")}
      style={{ color, borderColor: `${color}55`, background: `${color}10` }}
    >
      {v.tone === "key" && <Flame size={large ? 13 : 10} />}
      {v.label}
    </span>
  );
}

export function NoteCard({ f, index = 0, compact = false }: { f: Finding; index?: number; compact?: boolean }) {
  const s = SEVERITY[f.severity];
  const Icon = s.icon;
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={clsx("surface edge flex flex-col", compact ? "p-4" : "p-5")}
      style={edge(s.color)}
    >
      <div className="flex items-start gap-3">
        <Icon size={compact ? 16 : 18} className="mt-0.5 shrink-0" style={{ color: s.color }} />
        <div className="min-w-0 flex-1">
          <p className="eyebrow mb-1">{f.category}</p>
          <h3 className={clsx("font-semibold text-paper", compact ? "text-base" : "text-lg")}>{f.title}</h3>
        </div>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-mute">{f.detail}</p>
      {f.evidence.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
          {f.evidence.map((e) => (
            <div key={e.label}>
              <p className="text-[11px] tracking-widest text-dim uppercase">{e.label}</p>
              <p className="num text-paper">{e.value}</p>
            </div>
          ))}
        </div>
      )}
      {f.action && (
        <p className="mt-4 border-t border-line/60 pt-3 text-sm text-paper">
          <span className="text-gold">→ </span>
          {f.action}
        </p>
      )}
      {f.link && <NoteLink link={f.link} />}
    </motion.article>
  );
}

function NoteLink({ link }: { link: string }) {
  const onCoach = useLocation().pathname === "/coach";
  // Taller hit area on touch screens without changing the visual size.
  const cls = "eyebrow mt-3 inline-flex items-center gap-1 self-start hover:text-paper pointer-coarse:-my-2 pointer-coarse:py-3";
  if (link.startsWith("#") && onCoach) {
    return <a href={link} className={cls}>See chart <ArrowUpRight size={11} /></a>;
  }
  return (
    <Link to={link.startsWith("#") ? `/coach${link}` : link} className={cls}>
      {link.startsWith("#") ? "See in Coach" : "Open"} <ArrowUpRight size={11} />
    </Link>
  );
}

export function NoteGrid({ notes, compact = false }: { notes: Finding[]; compact?: boolean }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {notes.map((f, i) => (
        <NoteCard key={f.id} f={f} index={i} compact={compact} />
      ))}
    </div>
  );
}

/** One-line note rows for secondary context. */
export function NoteLines({ notes }: { notes: Finding[] }) {
  return (
    <ul className="divide-y divide-line/60">
      {notes.map((n) => (
        <li key={n.id} className="flex items-start gap-3 py-3">
          <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: SEVERITY[n.severity].color }} />
          <p className="min-w-0 text-sm">
            <span className="font-semibold text-paper">{n.title}.</span> <span className="text-mute">{n.detail}</span>
          </p>
        </li>
      ))}
    </ul>
  );
}

export function Ring({ score, size = 160, label = "readiness" }: { score: number; size?: number; label?: string }) {
  const color = readyColor(score);
  const r = 70;
  const circ = 2 * Math.PI * r;
  return (
    <motion.div
      data-ring-fit="coach-ring" data-inner="81"
      className="relative shrink-0"
      style={{ width: size, height: size }}
      initial={{ rotate: -140, scale: 0.85, opacity: 0 }}
      animate={{ rotate: 0, scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 70, damping: 16 }}
    >
      <span className="pointer-events-none absolute inset-[12%] rounded-full opacity-25 blur-2xl" style={{ background: color }} />
      <svg viewBox="0 0 160 160" className="relative h-full w-full -rotate-90">
        <circle cx="80" cy="80" r={r} fill="none" stroke={C.grid} strokeWidth="10" />
        <motion.circle
          cx="80" cy="80" r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - score / 100) }}
          transition={{ duration: 1.5, ease: [0.2, 0.9, 0.1, 1], delay: 0.15 }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <p className="num leading-none" style={{ color, fontSize: size * 0.3 }}>
            <CountUp value={score} format={round} duration={1.5} immediate />
          </p>
          <p className="eyebrow mt-1 !text-[11px]">{label}</p>
        </div>
      </div>
    </motion.div>
  );
}

const round = (v: number) => Math.round(v).toString();
