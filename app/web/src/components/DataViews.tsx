import { clsx } from "clsx";
import { ChevronRight, Search } from "lucide-react";
import { Fragment, useMemo, useState, type ReactNode } from "react";

/** camelCase / snake_case / numeric FIT ids -> readable label. */
export function humanize(key: string): string {
  return key
    .replace(/^field_(\d+)$/, "Field $1")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (c) => c.toUpperCase());
}

function seconds(v: number): string {
  const s = Math.round(v);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

const DURATION_KEY = /(duration|Duration|_time$|Time$|TimeInZone_\d|time_in_\w+zone|timer_time|elapsed_time|Seconds$)/;
const NOT_DURATION = /(start|end|local|gmt|timestamp|created|updated|zone$)/i;
const DISTANCE_KEY = /^(distance|total_distance|totalDistance|.*[dD]istance(InMeters)?)$/;
const SPEED_KEY = /(speed|Speed)$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const ID_KEY = /(Id|_id|Pk|PK|serial_number|uuid|Uuid)$/;

export interface Formatted {
  text: string;
  raw?: string;
}

/** Friendly rendering with the untouched value kept for the tooltip. */
export function formatValue(key: string, value: unknown): Formatted {
  if (value === null || value === undefined || value === "") return { text: "—" };
  if (typeof value === "boolean") return { text: value ? "Yes" : "No" };
  if (typeof value === "number") {
    const raw = String(value);
    if (ID_KEY.test(key)) return { text: raw };
    if (DURATION_KEY.test(key) && !NOT_DURATION.test(key) && value >= 0) return { text: seconds(value), raw: `${raw} s` };
    if (DISTANCE_KEY.test(key) && value > 0) return { text: `${(value / 1000).toFixed(2)} km`, raw: `${raw} m` };
    if (SPEED_KEY.test(key) && value > 0) return { text: `${(value * 3.6).toFixed(1)} km/h`, raw: `${raw} m/s` };
    if (Number.isInteger(value)) return { text: value.toLocaleString(), raw };
    return { text: Math.abs(value) >= 100 ? value.toFixed(1) : String(+value.toFixed(3)), raw };
  }
  if (typeof value === "string") {
    if (ISO.test(value)) {
      const d = new Date(value.length === 19 ? value : value);
      if (!Number.isNaN(d.getTime())) {
        return { text: d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }), raw: value };
      }
    }
    return { text: value.replace(/_/g, " ") };
  }
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v !== "object" || v === null)) {
      return { text: value.map((v) => formatValue(key, v).text).join(", ") || "—" };
    }
    return { text: `${value.length} items` };
  }
  return { text: "Object" };
}

function isScalar(v: unknown): boolean {
  return v === null || typeof v !== "object" || (Array.isArray(v) && v.every((x) => x === null || typeof x !== "object"));
}

export function Value({ k, v }: { k: string; v: unknown }) {
  const f = formatValue(k, v);
  return (
    <span className={clsx("num", f.text === "—" ? "text-dim" : "text-paper")} title={f.raw}>
      {f.text}
    </span>
  );
}

/** Every scalar field of an object, searchable; nested values open as trees. */
export function FieldGrid({ data, title }: { data: Record<string, unknown>; title?: ReactNode }) {
  const [q, setQ] = useState("");
  const [showEmpty, setShowEmpty] = useState(false);
  const entries = Object.entries(data);
  const empty = entries.filter(([, v]) => v === null || v === "" || (Array.isArray(v) && v.length === 0)).length;
  const shown = entries.filter(([k, v]) => {
    if (!showEmpty && (v === null || v === "" || (Array.isArray(v) && v.length === 0))) return false;
    if (!q) return true;
    const needle = q.toLowerCase();
    return k.toLowerCase().includes(needle) || humanize(k).toLowerCase().includes(needle);
  });
  const scalars = shown.filter(([, v]) => isScalar(v));
  const nested = shown.filter(([, v]) => !isScalar(v));

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        {title}
        <label className="ml-auto flex items-center gap-2 border border-line-strong px-3 py-1.5 text-sm">
          <Search size={14} className="text-dim" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={`Search ${entries.length} fields`}
            className="w-44 bg-transparent text-paper outline-none placeholder:text-dim"
          />
        </label>
        {empty > 0 && (
          <button type="button" onClick={() => setShowEmpty((s) => !s)} className="eyebrow hover:text-paper">
            {showEmpty ? "Hide" : "Show"} {empty} empty
          </button>
        )}
      </div>
      <dl className="grid gap-x-8 gap-y-0 sm:grid-cols-2 xl:grid-cols-3">
        {scalars.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-4 border-b border-line/70 py-2">
            <dt className="truncate text-xs text-mute" title={k}>
              {humanize(k)}
            </dt>
            <dd className="truncate text-right text-sm">
              <Value k={k} v={v} />
            </dd>
          </div>
        ))}
      </dl>
      {nested.length > 0 && (
        <div className="mt-4 space-y-1">
          {nested.map(([k, v]) => (
            <JsonTree key={k} name={k} value={v} />
          ))}
        </div>
      )}
      {shown.length === 0 && <p className="py-4 text-sm text-dim">No fields match.</p>}
    </div>
  );
}

function flatten(obj: Record<string, unknown>, prefix = "", out: Record<string, unknown> = {}): Record<string, unknown> {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v as Record<string, unknown>, key, out);
    else out[key] = v;
  }
  return out;
}

function label(key: string): string {
  return key.split(".").map(humanize).join(" › ");
}

/** Tabular view of uniform records (FIT messages, splits, sets). Nested objects become columns; rows with lists expand. */
export function RecordTable({
  rows,
  limit = 25,
  priority = [],
}: {
  rows: Record<string, unknown>[];
  limit?: number;
  priority?: string[];
}) {
  const [all, setAll] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const flat = useMemo(() => rows.map((r) => flatten(r)), [rows]);
  const columns = useMemo(() => {
    const seen = new Map<string, number>();
    for (const r of flat) for (const [k, v] of Object.entries(r)) if (v !== null && v !== undefined) seen.set(k, (seen.get(k) ?? 0) + 1);
    const keys = [...seen.keys()];
    return [...priority.filter((p) => seen.has(p)), ...keys.filter((k) => !priority.includes(k))];
  }, [flat, priority]);
  const visible = all ? flat : flat.slice(0, limit);
  if (!rows.length) return <p className="text-sm text-dim">No rows.</p>;
  return (
    <div>
      <div className="max-h-[520px] overflow-auto border border-line">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-coal">
            <tr>
              <th className="px-3 py-2 font-medium text-dim">#</th>
              {columns.map((c) => (
                <th key={c} className="px-3 py-2 font-medium whitespace-nowrap text-mute" title={c}>
                  {label(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {visible.map((r, i) => {
              const nested = columns.some((c) => !isScalar(r[c]));
              return (
                <Fragment key={i}>
                  <tr
                    className={clsx("hover:bg-slate/60", nested && "cursor-pointer")}
                    onClick={nested ? () => setExpanded(expanded === i ? null : i) : undefined}
                  >
                    <td className="num px-3 py-1.5 text-dim">
                      {nested && <ChevronRight size={11} className={clsx("mr-1 inline transition-transform", expanded === i && "rotate-90")} />}
                      {i + 1}
                    </td>
                    {columns.map((c) => (
                      <td key={c} className="px-3 py-1.5 whitespace-nowrap">
                        {isScalar(r[c]) ? (
                          <Value k={c.split(".").pop()!} v={r[c]} />
                        ) : (
                          <span className="text-gold">{(r[c] as unknown[]).length} items</span>
                        )}
                      </td>
                    ))}
                  </tr>
                  {expanded === i && (
                    <tr>
                      <td colSpan={columns.length + 1} className="bg-ink/60 px-4 py-3">
                        {columns
                          .filter((c) => !isScalar(r[c]))
                          .map((c) => (
                            <JsonTree key={c} name={c} value={r[c]} />
                          ))}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <button type="button" className="eyebrow mt-3 hover:text-paper" onClick={() => setAll((a) => !a)}>
          {all ? "Show fewer" : `Show all ${rows.length.toLocaleString()} rows`}
        </button>
      )}
    </div>
  );
}

/** Collapsible tree for any JSON value. Arrays of records render as tables. */
export function JsonTree({ name, value, depth = 0 }: { name: string; value: unknown; depth?: number }) {
  const [open, setOpen] = useState(depth < 1);
  if (isScalar(value)) {
    return (
      <div className="flex items-baseline justify-between gap-4 py-1 pl-5 text-sm">
        <span className="text-xs text-mute" title={name}>{humanize(name)}</span>
        <Value k={name} v={value} />
      </div>
    );
  }
  const isArray = Array.isArray(value);
  const items = isArray ? (value as unknown[]) : Object.entries(value as Record<string, unknown>);
  const recordArray = isArray && (value as unknown[]).every((v) => v && typeof v === "object" && !Array.isArray(v));
  return (
    <div className={clsx(depth > 0 && "border-l border-line pl-3")}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 py-1.5 text-left text-sm text-paper hover:text-gold"
      >
        <ChevronRight size={14} className={clsx("transition-transform", open && "rotate-90")} />
        <span className="font-semibold">{humanize(name)}</span>
        <span className="text-xs text-dim">
          {isArray ? `${items.length} items` : `${items.length} fields`}
        </span>
      </button>
      {open &&
        (recordArray ? (
          <div className="py-2 pl-5">
            <RecordTable rows={value as Record<string, unknown>[]} />
          </div>
        ) : isArray ? (
          (value as unknown[]).map((v, i) => <JsonTree key={i} name={`${humanize(name)} ${i + 1}`} value={v} depth={depth + 1} />)
        ) : (
          (items as [string, unknown][]).map(([k, v]) => <JsonTree key={k} name={k} value={v} depth={depth + 1} />)
        ))}
    </div>
  );
}
