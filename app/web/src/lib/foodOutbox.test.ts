import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { backoffMs, createOutbox, isRetryable, memoryStore, sendLogOp, resetBatchSupport } from "./foodOutbox";
import type { LogOp } from "./foodTypes";

const op = (key: string, extra: Partial<LogOp> = {}): LogOp => ({
  key, day: "2026-11-08", meal: "breakfast", items: [{ dish_id: 1, servings: 2 }], created_at: Date.now() + Number(key.replace(/\D/g, "") || 0), attempts: 0, status: "queued", preview: [], ...extra,
});

describe("outbox", () => {
  it("sends straight away when online", async () => {
    const send = vi.fn(async () => ({ ids: [7] }));
    const ob = createOutbox(memoryStore(), send);
    expect(await ob.submit(op("a1"))).toEqual({ status: "sent", ids: [7] });
    expect(await ob.list()).toEqual([]);
  });

  it("queues on a network failure and replays in order with the same keys, once each", async () => {
    let online = false;
    const seen: string[] = [];
    const send = vi.fn(async (o: LogOp) => {
      if (!online) throw new ApiError(0, "offline", "offline");
      seen.push(o.key);
      return { ids: [] };
    });
    const ob = createOutbox(memoryStore(), send);
    expect((await ob.submit(op("a1"))).status).toBe("queued");
    expect((await ob.submit(op("a2"))).status).toBe("queued"); // not sent ahead of the waiting one
    expect(send).toHaveBeenCalledTimes(1);
    expect((await ob.flush()).left).toBe(2); // still offline: stops at the first
    online = true;
    expect(await ob.flush()).toEqual({ sent: 2, left: 0 });
    expect(seen).toEqual(["a1", "a2"]);
    expect(await ob.flush()).toEqual({ sent: 0, left: 0 }); // nothing replayed twice
  });

  it("stops on a 4xx and marks it for a look instead of retrying forever", async () => {
    const send = vi.fn(async (o: LogOp) => {
      if (o.key === "a1") throw new ApiError(400, "Item 1: unknown dish");
      return { ids: [] };
    });
    const store = memoryStore();
    const ob = createOutbox(store, send);
    await store.put(op("a1"));
    await store.put(op("a2"));
    const r = await ob.flush();
    expect(r.sent).toBe(1); // a2 still goes: a bad op does not block the rest
    const left = await ob.list();
    expect(left).toHaveLength(1);
    expect(left[0]).toMatchObject({ key: "a1", status: "needs_look", error: "Item 1: unknown dish" });
    await ob.retry("a1");
    expect((await ob.list())[0].status).toBe("queued");
    await ob.discard("a1");
    expect(await ob.list()).toEqual([]);
  });

  it("rejects a 4xx on submit so the draft is kept", async () => {
    const ob = createOutbox(memoryStore(), async () => { throw new ApiError(400, "bad"); });
    await expect(ob.submit(op("a1"))).rejects.toThrow("bad");
    expect(await ob.list()).toEqual([]);
  });

  it("classifies errors and backs off", () => {
    expect(isRetryable(new ApiError(0, "x", "timeout"))).toBe(true);
    expect(isRetryable(new ApiError(503, "x"))).toBe(true);
    expect(isRetryable(new ApiError(429, "x"))).toBe(true);
    expect(isRetryable(new ApiError(404, "x"))).toBe(false);
    expect(isRetryable(new TypeError("fetch failed"))).toBe(true);
    expect([1, 2, 3, 20].map(backoffMs)).toEqual([5000, 10000, 20000, 300000]);
  });
});

describe("sendLogOp", () => {
  beforeEach(() => {
    resetBatchSupport();
    vi.restoreAllMocks();
  });
  const respond = (handler: (url: string, init: RequestInit) => Response | Promise<Response>) =>
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u, i) => handler(String(u), (i ?? {}) as RequestInit));
  const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });

  it("uses the batch endpoint with the idempotency key as header and client_key", async () => {
    const calls: { url: string; headers: Headers; body: Record<string, unknown> }[] = [];
    respond((url, init) => {
      calls.push({ url, headers: new Headers(init.headers), body: JSON.parse(String(init.body)) });
      return json({ entries: [{ id: 5 }, { id: 6 }] });
    });
    const r = await sendLogOp(op("k1", { items: [{ dish_id: 1, servings: 1 }, { dish_id: 2, grams: 100 }] }));
    expect(r.ids).toEqual([5, 6]);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/api/food/log");
    expect(calls[0].headers.get("Idempotency-Key")).toBe("k1");
    expect(calls[0].body.client_key).toBe("k1");
  });

  it("falls back to one request per item with keys {key}:{i} when the batch route is absent", async () => {
    const keys: (string | null)[] = [];
    respond((url, init) => {
      if (url.includes("/api/food/log")) return json({ detail: "Not Found" }, 404);
      keys.push(new Headers(init.headers).get("Idempotency-Key"));
      return json({ id: keys.length });
    });
    const r = await sendLogOp(op("k2", { items: [{ dish_id: 1, servings: 1 }, { name: "Biryani", kcal: 450, protein_g: null, save_dish: false }] }));
    expect(keys).toEqual(["k2:0", "k2:1"]);
    expect(r.ids).toEqual([1, 2]);
  });
});
