import { describe, expect, it, vi } from "vitest";
import { addKey, alsoLine, applyPending, cleanName, createNameQueue, displayName, memoryNameStore, nameSuggestions, newAddOp, validateMyName, withMyName, withoutMyName, withPreferred, type NameOp } from "./foodNames";
import { ApiError } from "./api";
import { isRetryable } from "./foodOutbox";
import type { FoodDish } from "./types";

const dish = (extra: Partial<FoodDish> = {}) => ({ id: 7, name: "Sweet curd", aliases: ["Mishti doi", "Dahi"], ...extra }) as FoodDish;

describe("validation", () => {
  it("accepts a clean name and tidies spaces", () => {
    expect(validateMyName("  Meetha   dahi ", dish())).toEqual({ ok: true, name: "Meetha dahi" });
    expect(cleanName("a\tb\n")).toBe("a b");
    expect(validateMyName("मीठा दही", dish())).toEqual({ ok: true, name: "मीठा दही" });
  });
  it("rejects empty, long, letterless and repeated names", () => {
    expect(validateMyName("   ", dish()).ok).toBe(false);
    expect(validateMyName("x".repeat(80), dish()).ok).toBe(false);
    expect(validateMyName("!! ??", dish()).ok).toBe(false);
    expect(validateMyName("sweet curd", dish()).ok).toBe(false);
    expect(validateMyName("Meethaa dahi", dish({ my_names: [{ id: 1, name: "Meetha dahi" }] })).ok).toBe(false); // same after spelling folds
  });
  it("caps names per dish", () => {
    const many = Array.from({ length: 12 }, (_, i) => ({ id: i + 1, name: `name${String.fromCharCode(97 + i)}` }));
    expect(validateMyName("another", dish({ my_names: many })).ok).toBe(false);
  });
});

describe("display", () => {
  it("shows your preferred name first, with the library name beneath", () => {
    const d = dish({ my_names: [{ id: 1, name: "Meetha dahi", preferred: true }] });
    expect(displayName(d)).toBe("Meetha dahi");
    expect(alsoLine(d)).toBe("also: Sweet curd");
  });
  it("falls back to the server display name, then the library name", () => {
    expect(displayName(dish({ display_name: "Mishti" }))).toBe("Mishti");
    expect(displayName(dish({ my_names: [{ id: 1, name: "X" }] }))).toBe("Sweet curd");
    expect(alsoLine(dish())).toBeNull();
  });
  it("suggests library spellings not yet used", () => {
    expect(nameSuggestions(dish({ my_names: [{ id: 1, name: "dahi" }] }))).toEqual(["Mishti doi"]);
    expect(nameSuggestions(dish(), "mi")).toEqual(["Mishti doi", "Dahi"]);
    expect(nameSuggestions({ name: "X" })).toEqual([]);
  });
});

describe("optimistic edits", () => {
  it("add, prefer and remove", () => {
    let all = [dish(), dish({ id: 8, name: "Other" })];
    all = withMyName(all, 7, "Meetha dahi", true, -1);
    expect(displayName(all[0])).toBe("Meetha dahi");
    all = withMyName(all, 7, "Mishti", false, -2);
    expect(displayName(all[0])).toBe("Meetha dahi");
    all = withPreferred(all, 7, -2, true);
    expect(displayName(all[0])).toBe("Mishti");
    expect(all[0].my_names?.filter((m) => m.preferred)).toHaveLength(1);
    all = withoutMyName(all, 7, -2);
    expect(displayName(all[0])).toBe("Sweet curd");
    expect(all[1].my_names).toBeUndefined();
  });
});

describe("offline queue", () => {
  const offline = () => new ApiError(0, "offline", "offline");
  const make = (send: (op: NameOp) => Promise<void>) => createNameQueue(memoryNameStore(), send, isRetryable, (e) => e instanceof ApiError && e.status === 409);

  it("sends straight away when online", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    const q = make(send);
    expect(await q.submit(newAddOp(7, "Meetha dahi", true))).toBe("sent");
    expect(q.list()).toHaveLength(0);
  });
  it("queues offline, replays in order, once, and survives a double tap", async () => {
    let up = false;
    const sent: string[] = [];
    const q = make(async (op) => { if (!up) throw offline(); sent.push(op.key); });
    const a = newAddOp(7, "Meetha dahi", true);
    expect(await q.submit(a)).toBe("queued");
    expect(await q.submit({ ...a })).toBe("queued");
    await q.submit(newAddOp(7, "Mishti", false));
    expect(q.list()).toHaveLength(2);
    expect((await q.flush()).left).toBe(2);
    up = true;
    expect(await q.flush()).toEqual({ sent: 2, left: 0 });
    expect(sent).toEqual([addKey(7, "Meetha dahi"), addKey(7, "Mishti")]);
  });
  it("a duplicate reply counts as done; a refusal needs a look; an already-gone remove is fine", async () => {
    const q = make(async (op) => { throw new ApiError(op.kind === "add" && op.name === "dup" ? 409 : op.kind === "remove" ? 404 : 400, "no"); });
    expect(await q.submit(newAddOp(7, "dup", false))).toBe("sent");
    await expect(q.submit(newAddOp(7, "bad", false))).rejects.toBeInstanceOf(ApiError);
    expect(await q.submit({ key: "r", kind: "remove", dish_id: 7, alias_id: 5, created_at: 0, attempts: 0, status: "queued" })).toBe("sent");
  });
  it("removing or preferring a name that is still only queued edits the queued add", async () => {
    const q = make(async () => { throw offline(); });
    const a = newAddOp(7, "Meetha dahi", false);
    await q.submit(a);
    await q.submit({ key: "p", kind: "prefer", dish_id: 7, alias_id: a.local_id, preferred: true, created_at: 0, attempts: 0, status: "queued" });
    expect(q.list()).toHaveLength(1);
    expect((q.list()[0] as { preferred: boolean }).preferred).toBe(true);
    await q.submit({ key: "x", kind: "remove", dish_id: 7, alias_id: a.local_id, created_at: 0, attempts: 0, status: "queued" });
    expect(q.list()).toHaveLength(0);
  });
  it("queued edits show on top of the server list", () => {
    const ops: NameOp[] = [newAddOp(7, "Meetha dahi", true)];
    expect(displayName(applyPending([dish()], ops)[0])).toBe("Meetha dahi");
    const already = dish({ my_names: [{ id: 3, name: "Meetha dahi", preferred: true }] });
    expect(applyPending([already], ops)[0].my_names).toHaveLength(1);
  });
});
