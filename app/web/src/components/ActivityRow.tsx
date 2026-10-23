import { clsx } from "clsx";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import { VerdictChip } from "./CoachNotes";
import { formatDuration, formatKm, formatPace, parseDay } from "../lib/format";
import { activityStyle } from "../lib/metrics";
import type { ActivityItem } from "../lib/types";

const monthFmt = new Intl.DateTimeFormat(undefined, { month: "short" });
const weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short" });

function IntensityStrip({ i }: { i: NonNullable<ActivityItem["intensity"]> }) {
  return (
    <span
      className="hidden h-1.5 w-14 shrink-0 overflow-hidden sm:flex"
      title={`Easy ${i.easy_pct}% · Z3 ${i.moderate_pct}% · Hard ${i.hard_pct}%`}
      aria-label={`Easy ${i.easy_pct}%, zone 3 ${i.moderate_pct}%, hard ${i.hard_pct}%`}
    >
      <span style={{ width: `${i.easy_pct}%`, background: "#5be3b0" }} />
      <span style={{ width: `${i.moderate_pct}%`, background: "#c8f560" }} />
      <span style={{ width: `${i.hard_pct}%`, background: "#ff6a55" }} />
    </span>
  );
}

export function ActivityRow({ a, compact = false }: { a: ActivityItem; compact?: boolean }) {
  const style = activityStyle(a.type, a.family);
  const Icon = style.icon;
  const day = parseDay(a.local_date);
  const pace = a.family === "run" ? formatPace(a.duration_s, a.distance_m) : null;
  const stats = [
    a.distance_m != null && { label: "km", value: formatKm(a.distance_m) },
    { label: "time", value: formatDuration(a.duration_s) },
    pace && { label: "/km", value: pace },
    !compact && a.avg_hr != null && { label: "bpm", value: Math.round(a.avg_hr).toString() },
    !compact && a.training_load != null && { label: "load", value: Math.round(a.training_load).toString() },
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <li>
      <Link
        to={`/activities/${a.id}`}
        className={clsx(
          "group -mx-3 flex items-center gap-4 px-3 transition-colors hover:bg-slate/60",
          compact ? "py-3.5" : "py-5",
        )}
      >
      <div className="w-12 shrink-0 text-center">
        <p className="font-display text-3xl leading-none text-cream">{day.getDate()}</p>
        <p className="eyebrow mt-1 !text-[10px]">
          {compact ? weekdayFmt.format(day) : monthFmt.format(day)}
        </p>
      </div>
      <div
        className="grid h-10 w-10 shrink-0 place-items-center"
        style={{ background: `${style.color}1a`, color: style.color }}
      >
        <Icon size={18} strokeWidth={1.75} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-paper">{a.name}</p>
        <p className="flex items-center gap-2 text-xs text-mute">
          {style.label}
          {a.intensity && <IntensityStrip i={a.intensity} />}
          {a.verdict && <VerdictChip v={a.verdict} />}
        </p>
      </div>
      <dl className="flex gap-5 text-right sm:gap-7">
        {stats.map((s, i) => (
          <div key={s.label} className={clsx(i >= 1 && "hidden sm:block", i >= 2 && "sm:hidden md:block")}>
            <dd className="num text-base text-paper sm:text-lg">{s.value}</dd>
            <dt className="text-[10px] tracking-widest text-dim uppercase">{s.label}</dt>
          </div>
        ))}
      </dl>
      <ChevronRight size={16} className="shrink-0 text-dim transition-transform group-hover:translate-x-0.5 group-hover:text-paper" />
      </Link>
    </li>
  );
}
