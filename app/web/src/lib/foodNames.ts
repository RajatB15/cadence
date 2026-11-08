/**
 * "My name" for a dish: validation, display, suggestions, optimistic edits and an offline retry queue. Pure and offline; the
 * server is only reached through the injected sender, so everything is testable without a browser. Your own names are kept
 * apart from the library's aliases and are never presented as library data. No LLM.
 */
import { foldKey } from "./foodParse";
import type { FoodDish, MyName } from "./types";

export const MAX_NAME_LEN = 60;
export const MAX_MY_NAMES = 12;

type NameDish = Pick<FoodDish, "name"> & Partial<Pick<FoodDish, "aliases" | "my_names" | "display_name">>;

/** Trim, collapse spaces, strip control characters. */
export const cleanName = (s: string): string => s.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim();

export type NameCheck = { ok: true; name: string } | { ok: false; reason: string };

/** Is this a usable name for the dish? Rejects empty, too long, no letters, a repeat of a name the dish already has. */
export function validateMyName(raw: string, dish: NameDish): NameCheck {
  const name = cleanName(raw);
  if (!name) return { ok: false, reason: "Type a name first." };
  if (name.length > MAX_NAME_LEN) return { ok: false, reason: `Keep it under ${MAX_NAME_LEN + 1} characters.` };
  if (!/[\p{L}\p{N}]/u.test(name)) return { ok: false, reason: "Use at least one letter or digit." };
  const key = foldKey(name);
  if (!key) return { ok: false, reason: "Use at least one letter or digit." };
  if ((dish.my_names ?? []).some((m) => foldKey(m.name) === key)) return { ok: false, reason: "You already named it that." };
  if ((dish.my_names ?? []).length >= MAX_MY_NAMES) return { ok: false, reason: `A dish can have ${MAX_MY_NAMES} names of your own.` };
  if (foldKey(dish.name) === key) return { ok: false, reason: "That is already the dish's name." };
  return { ok: true, name };
}

/** The name to show first: your preferred name, else the server's display name, else the library name. */
export function displayName(d: NameDish): string {
  const pref = (d.my_names ?? []).find((m) => m.preferred);
  return pref?.name || d.display_name || d.name;
}

/** "also: <library name>" when a name of yours (or the server's display name) leads; null otherwise. */
export function alsoLine(d: NameDish): string | null {
  const shown = displayName(d);
  return shown !== d.name ? `also: ${d.name}` : null;
}

/** Library spellings worth offering as your name: aliases not yet used, plus the typed text first. Capped for the phone. */
export function nameSuggestions(d: NameDish, typed = "", limit = 6): string[] {
  const taken = new Set([foldKey(d.name), ...(d.my_names ?? []).map((m) => foldKey(m.name))]);
  const out: string[] = [];
  for (const a of d.aliases ?? []) {
    const c = cleanName(a);
    const k = foldKey(c);
    if (!c || !k || taken.has(k)) continue;
    taken.add(k);
    out.push(c);
  }
  const t = foldKey(typed);
  const lead = (s: string) => (t && foldKey(s).startsWith(t) ? 0 : 1);
  return out.sort((a, b) => lead(a) - lead(b)).slice(0, limit);
}

// ---- optimistic edits (applied to the dish list in the cache) -----------------------------------------------------

let tempSeq = 0;
const tempId = () => -(Date.now() % 1_000_000_000) - ++tempSeq;

const mapDish = (dishes: FoodDish[], id: number, f: (d: FoodDish) => FoodDish) => dishes.map((d) => (d.id === id ? f(d) : d));

export function withMyName(dishes: FoodDish[], dishId: number, name: string, preferred: boolean, id = tempId()): FoodDish[] {
  return mapDish(dishes, dishId, (d) => {
    const key = foldKey(name);
    const existing = (d.my_names ?? []).filter((m) => foldKey(m.name) !== key).map((m) => (preferred ? { ...m, preferred: false } : m));
    const names: MyName[] = [...existing, { id, name, preferred }];
    return { ...d, my_names: names, display_name: preferred ? name : d.display_name };
  });
}

export function withoutMyName(dishes: FoodDish[], dishId: number, aliasId: number): FoodDish[] {
  return mapDish(dishes, dishId, (d) => {
    const gone = (d.my_names ?? []).find((m) => m.id === aliasId);
    const names = (d.my_names ?? []).filter((m) => m.id !== aliasId);
    return { ...d, my_names: names, display_name: gone?.preferred || d.display_name === gone?.name ? undefined : d.display_name };
  });
}

export function withPreferred(dishes: FoodDish[], dishId: number, aliasId: number, preferred: boolean): FoodDish[] {
  return mapDish(dishes, dishId, (d) => {
    const names = (d.my_names ?? []).map((m) => ({ ...m, preferred: m.id === aliasId ? preferred : preferred ? false : m.preferred }));
    const now = names.find((m) => m.preferred);
    return { ...d, my_names: names, display_name: now?.name };
  });
}

// ---- offline queue -------------------------------------------------------------------------------------------------

export type NameOp =
  | { key: string; kind: "add"; dish_id: number; name: string; preferred: boolean; local_id: number; created_at: number; attempts: number; status: "queued" | "needs_look"; error?: string | null }
  | { key: string; kind: "remove"; dish_id: number; alias_id: number; created_at: number; attempts: number; status: "queued" | "needs_look"; error?: string | null }
  | { key: string; kind: "prefer"; dish_id: number; alias_id: number; preferred: boolean; created_at: number; attempts: number; status: "queued" | "needs_look"; error?: string | null };

/** Same dish and same folded name always give the same key, so a retry (or a double tap) cannot add it twice. */
export const addKey = (dishId: number, name: string) => `name:${dishId}:${foldKey(name)}`;

export interface NameStore {
  read(): NameOp[];
  write(ops: NameOp[]): void;
}

export function memoryNameStore(): NameStore {
  let ops: NameOp[] = [];
  return { read: () => ops, write: (o) => void (ops = o) };
}

const LS_KEY = "cadence-food-name-ops";
/** localStorage-backed; any failure (private window, blocked storage) falls back to memory. */
export function localNameStore(): NameStore {
  const mem = memoryNameStore();
  return {
    read() {
      try {
        const v = JSON.parse(localStorage.getItem(LS_KEY) ?? "[]");
        return Array.isArray(v) ? (v as NameOp[]) : [];
      } catch {
        return mem.read();
      }
    },
    write(ops) {
      mem.write(ops);
      try {
        localStorage.setItem(LS_KEY, JSON.stringify(ops));
      } catch {
        /* memory copy only */
      }
    },
  };
}

export type NameSender = (op: NameOp) => Promise<void>;

export interface NameQueue {
  list(): NameOp[];
  /** Try now; on a retryable failure keep it queued. Resolves "sent" or "queued"; rejects when the server refuses it (4xx). */
  submit(op: NameOp): Promise<"sent" | "queued">;
  flush(): Promise<{ sent: number; left: number }>;
  discard(key: string): void;
  subscribe(fn: () => void): () => void;
}

/**
 * @param retryable decides whether a failure keeps the op queued (injected so this file does not import the API client)
 * @param duplicate a "already exists" reply on add counts as success
 */
export function createNameQueue(store: NameStore, send: NameSender, retryable: (e: unknown) => boolean, duplicate: (e: unknown) => boolean = () => false): NameQueue {
  const subs = new Set<() => void>();
  const changed = () => subs.forEach((f) => f());
  const put = (ops: NameOp[]) => (store.write(ops), changed());
  const run = async (op: NameOp) => {
    try {
      await send(op);
    } catch (e) {
      if (op.kind === "add" && duplicate(e)) return;
      if (op.kind === "remove" && e && typeof e === "object" && (e as { status?: number }).status === 404) return; // already gone
      throw e;
    }
  };
  let flushing: Promise<{ sent: number; left: number }> | null = null;
  const q: NameQueue = {
    list: () => store.read(),
    async submit(op) {
      const ops = store.read();
      // Removing a name that was only ever queued: cancel the add instead of sending two requests.
      if (op.kind === "remove") {
        const pending = ops.find((o) => o.kind === "add" && o.local_id === op.alias_id && o.dish_id === op.dish_id);
        if (pending) return put(ops.filter((o) => o !== pending)), "sent";
      }
      if (op.kind === "prefer") {
        const pending = ops.find((o) => o.kind === "add" && o.local_id === op.alias_id && o.dish_id === op.dish_id);
        if (pending && pending.kind === "add") return put(ops.map((o) => (o === pending ? { ...pending, preferred: op.preferred } : o))), "sent";
      }
      if (ops.some((o) => o.key === op.key)) return "queued"; // double tap
      if (ops.filter((o) => o.status === "queued").length === 0) {
        try {
          await run(op);
          return "sent";
        } catch (e) {
          if (!retryable(e)) throw e;
        }
      }
      put([...store.read(), op]);
      return "queued";
    },
    flush() {
      flushing ??= (async () => {
        let sent = 0;
        try {
          for (const op of [...store.read()]) {
            if (op.status !== "queued") continue;
            try {
              await run(op);
              put(store.read().filter((o) => o.key !== op.key));
              sent++;
            } catch (e) {
              if (retryable(e)) {
                put(store.read().map((o) => (o.key === op.key ? { ...o, attempts: o.attempts + 1 } : o)));
                break;
              }
              put(store.read().map((o) => (o.key === op.key ? { ...o, status: "needs_look" as const, error: e instanceof Error ? e.message : "Could not be saved" } : o)));
            }
          }
        } finally {
          flushing = null;
        }
        return { sent, left: store.read().length };
      })();
      return flushing;
    },
    discard(key) {
      put(store.read().filter((o) => o.key !== key));
    },
    subscribe(fn) {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
  };
  return q;
}

/** Show queued edits on top of what the server sent, so a reload while offline still shows your names. */
export function applyPending(dishes: FoodDish[], ops: NameOp[]): FoodDish[] {
  let out = dishes;
  for (const op of ops) {
    if (op.status !== "queued") continue;
    if (op.kind === "add") {
      const has = out.find((d) => d.id === op.dish_id)?.my_names?.some((m) => foldKey(m.name) === foldKey(op.name));
      if (!has) out = withMyName(out, op.dish_id, op.name, op.preferred, op.local_id);
    } else if (op.kind === "remove") out = withoutMyName(out, op.dish_id, op.alias_id);
    else out = withPreferred(out, op.dish_id, op.alias_id, op.preferred);
  }
  return out;
}

export const newAddOp = (dishId: number, name: string, preferred: boolean): Extract<NameOp, { kind: "add" }> => ({
  key: addKey(dishId, name), kind: "add", dish_id: dishId, name, preferred, local_id: tempId(), created_at: Date.now(), attempts: 0, status: "queued",
});
