/**
 * Offline outbox for food logging (docs/food-logging-design.md 2h): an IndexedDB queue of "log this draft" requests, replayed in
 * order when back online. Each request carries one idempotency key generated when the draft was submitted and reused on every
 * retry, so a replay never duplicates. IndexedDB failures fall back to memory; nothing here throws into the UI.
 * The store and the sender are injected so the logic is testable without a browser.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { LogOp } from "./foodTypes";
import type { FoodEntryInput } from "./types";
import type { LogItem } from "./foodRow";

export interface OutboxStore {
  all(): Promise<LogOp[]>;
  put(op: LogOp): Promise<void>;
  del(key: string): Promise<void>;
}

export function memoryStore(): OutboxStore {
  const m = new Map<string, LogOp>();
  return {
    all: async () => [...m.values()].sort((a, b) => a.created_at - b.created_at),
    put: async (op) => void m.set(op.key, op),
    del: async (key) => void m.delete(key),
  };
}

const DB = "cadence-food-outbox";
const STORE = "ops";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    req.onblocked = () => reject(new Error("blocked"));
  });
}

/** IndexedDB-backed store; any failure switches that call (and later ones) to the in-memory copy. */
export function indexedDbStore(): OutboxStore {
  const fallback = memoryStore();
  let broken = typeof indexedDB === "undefined";
  let db: Promise<IDBDatabase> | null = null;
  const run = async <T>(mode: IDBTransactionMode, f: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> => {
    db ??= openDb();
    const d = await db;
    return new Promise<T>((resolve, reject) => {
      const req = f(d.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  };
  const guard = async <T>(f: () => Promise<T>, g: () => Promise<T>): Promise<T> => {
    if (broken) return g();
    try {
      return await f();
    } catch {
      broken = true;
      return g();
    }
  };
  return {
    all: () => guard(async () => ((await run("readonly", (s) => s.getAll())) as LogOp[]).sort((a, b) => a.created_at - b.created_at), fallback.all),
    put: (op) => guard(async () => void (await run("readwrite", (s) => s.put(op))), () => fallback.put(op)),
    del: (key) => guard(async () => void (await run("readwrite", (s) => s.delete(key))), () => fallback.del(key)),
  };
}

export type SendFn = (op: LogOp) => Promise<{ ids: number[] }>;

/** Retryable: no connection, a timeout, a server error, or a throttle. Anything else (4xx) needs a human. */
export function isRetryable(e: unknown): boolean {
  if (!(e instanceof ApiError)) return true;
  if (e.kind === "offline" || e.kind === "timeout") return true;
  return e.status >= 500 || e.status === 408 || e.status === 429 || e.status === 0;
}

let batchSupported: boolean | null = null;
/** Test hook. */
export const resetBatchSupport = () => void (batchSupported = null);

const entryFor = (op: LogOp, item: LogItem): FoodEntryInput => ({
  day: op.day,
  meal: op.meal,
  eating_out: op.eating_out,
  ...(item.dish_id != null ? { dish_id: item.dish_id, ...(item.grams != null ? { grams: item.grams } : { servings: item.servings }) } : { name: item.name, kcal: item.kcal, protein_g: item.protein_g ?? null, save_dish: item.save_dish ?? false }),
});

const idOf = (e: unknown): number[] => (e && typeof e === "object" && typeof (e as { id?: unknown }).id === "number" ? [(e as { id: number }).id] : []);

/**
 * Sends one op: the batch endpoint when the server has it, otherwise one entry request per item with the key "{key}:{i}"
 * (the same keys the batch endpoint uses, so a half-sent op resumes on either path without duplicating).
 */
export const sendLogOp: SendFn = async (op) => {
  if (batchSupported !== false) {
    try {
      const res = await api.foodLogBatch({ day: op.day, meal: op.meal, eaten_at: op.eaten_at, eating_out: op.eating_out, source: op.source, items: op.items }, op.key);
      batchSupported = true;
      return { ids: (res?.entries ?? []).flatMap(idOf) };
    } catch (e) {
      if (!(e instanceof ApiError) || (e.status !== 404 && e.status !== 405)) throw e;
      batchSupported = false; // an older server, or a phone not yet allowed to use it
    }
  }
  const ids: number[] = [];
  for (let i = 0; i < op.items.length; i++) ids.push(...idOf(await api.addFoodEntry(entryFor(op, op.items[i]), `${op.key}:${i}`)));
  return { ids };
};

export interface Outbox {
  list(): Promise<LogOp[]>;
  /** Try now; if the network or server is unavailable, queue it. Resolves "sent" with new entry ids, or "queued". Rejects on 4xx. */
  submit(op: LogOp): Promise<{ status: "sent"; ids: number[] } | { status: "queued" }>;
  flush(): Promise<{ sent: number; left: number }>;
  discard(key: string): Promise<void>;
  /** Mark a "needs a look" op queued again after the user fixed or accepted it. */
  retry(key: string): Promise<void>;
  subscribe(fn: () => void): () => void;
}

export function createOutbox(store: OutboxStore, send: SendFn): Outbox {
  const subs = new Set<() => void>();
  const changed = () => subs.forEach((f) => f());
  let flushing: Promise<{ sent: number; left: number }> | null = null;
  const outbox: Outbox = {
    list: () => store.all(),
    async submit(op) {
      // Keep order: anything already waiting goes first, so a later draft never overtakes an earlier one.
      const waiting = (await store.all()).filter((o) => o.status === "queued");
      if (waiting.length === 0) {
        try {
          const { ids } = await send(op);
          return { status: "sent", ids };
        } catch (e) {
          if (!isRetryable(e)) throw e;
        }
      }
      await store.put({ ...op, attempts: op.attempts, status: "queued" });
      changed();
      return { status: "queued" };
    },
    flush() {
      flushing ??= (async () => {
        let sent = 0;
        try {
          for (const op of await store.all()) {
            if (op.status !== "queued") continue;
            try {
              await send(op);
              await store.del(op.key);
              sent++;
            } catch (e) {
              if (isRetryable(e)) {
                await store.put({ ...op, attempts: op.attempts + 1 });
                break; // keep order; try again later
              }
              await store.put({ ...op, status: "needs_look", error: e instanceof Error ? e.message : "Could not be saved" });
            }
          }
        } finally {
          flushing = null;
          changed();
        }
        const left = (await store.all()).length;
        return { sent, left };
      })();
      return flushing;
    },
    async discard(key) {
      await store.del(key);
      changed();
    },
    async retry(key) {
      const op = (await store.all()).find((o) => o.key === key);
      if (op) await store.put({ ...op, status: "queued", error: null });
      changed();
    },
    subscribe(fn) {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
  };
  return outbox;
}

export const outbox = createOutbox(indexedDbStore(), sendLogOp);

/** Backoff between automatic flush attempts: 5 s, doubling, capped at 5 minutes. */
export const backoffMs = (attempts: number) => Math.min(300_000, 5_000 * 2 ** Math.max(0, attempts - 1));

/** The waiting ops, refreshed on change; also flushes on reconnect, on returning to the app and on a backoff timer. */
export function useOutbox(): { ops: LogOp[]; flush: () => void } {
  const [ops, setOps] = useState<LogOp[]>([]);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      const all = await outbox.list().catch(() => [] as LogOp[]);
      if (!alive) return all;
      setOps(all);
      clearTimeout(timer);
      const next = all.find((o) => o.status === "queued");
      if (next) timer = setTimeout(() => void attempt(), backoffMs(next.attempts));
      return all;
    };
    const attempt = async () => {
      clearTimeout(timer);
      await outbox.flush().catch(() => undefined);
      await load();
    };
    const unsub = outbox.subscribe(() => void load());
    const onOnline = () => void attempt();
    const onVisible = () => { if (document.visibilityState === "visible") void attempt(); };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);
    void attempt();
    return () => {
      alive = false;
      clearTimeout(timer);
      unsub();
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return { ops, flush: () => void outbox.flush() };
}
