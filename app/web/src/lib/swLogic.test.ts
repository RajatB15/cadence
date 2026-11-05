import swLogicSource from "../../public/sw-logic.js?raw";
import { describe, expect, it } from "vitest";
import { MIGHT_HAVE_SAVED, apiFetch, keyFor, markWrite, wantsFresh } from "./api";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const L: any = (() => {
  const m = { exports: {} as unknown };
  new Function("module", swLogicSource)(m);
  return m.exports;
})();
const res = (init: { ok?: boolean; type?: string; ct?: string; cc?: string }) =>
  ({ ok: init.ok ?? true, type: init.type ?? "basic", headers: new Headers({ "Content-Type": init.ct ?? "", "Cache-Control": init.cc ?? "" }) }) as unknown as Response;

describe("service worker logic", () => {
  it("flags auth failures", () => {
    expect(L.isAuthFailure(401)).toBe(true);
    expect(L.isAuthFailure(403)).toBe(true);
    expect(L.isAuthFailure(500)).toBe(false);
  });
  it("does not cache HTML (SPA fallback) as an asset", () => {
    expect(L.assetCacheable(res({ ct: "text/html; charset=utf-8" }))).toBe(false);
    expect(L.assetCacheable(res({ ct: "text/javascript" }))).toBe(true);
    expect(L.assetCacheable(res({ ok: false, ct: "text/javascript" }))).toBe(false);
  });
  it("honours the fresh header and /pair clearing", () => {
    expect(L.wantsFresh(new Headers({ "X-Cadence-Fresh": "1" }))).toBe(true);
    expect(L.wantsFresh(new Headers())).toBe(false);
    expect(L.clearsOnNavigate("/pair")).toBe(true);
    expect(L.clearsOnNavigate("/pair/abc")).toBe(true);
    expect(L.clearsOnNavigate("/pairing")).toBe(false);
  });
  it("prunes old caches and assets", () => {
    expect(L.staleCaches(["cadence-data-v1", "cadence-data-v2", "other"], ["cadence-data-v2"])).toEqual(["cadence-data-v1"]);
    expect(L.pruneKeys([1, 2, 3, 4], 2)).toEqual([1, 2]);
    expect(L.pruneKeys([1], 2)).toEqual([]);
  });
});

describe("client freshness and idempotency", () => {
  it("asks for fresh data for 30 s after a write", () => {
    markWrite(1_000_000);
    expect(wantsFresh(1_010_000)).toBe(true);
    expect(wantsFresh(1_100_000)).toBe(false);
  });
  it("reuses a key for the same payload and renews it when the payload changes", () => {
    const slot = { current: null as { sig: string; key: string } | null };
    const a = keyFor(slot, { x: 1 });
    expect(keyFor(slot, { x: 1 })).toBe(a);
    expect(keyFor(slot, { x: 2 })).not.toBe(a);
  });
  it("tells the user a timed-out write might have saved", async () => {
    const orig = globalThis.fetch;
    globalThis.fetch = ((_: unknown, init: RequestInit) =>
      new Promise((_r, rej) => init.signal!.addEventListener("abort", () => rej(new DOMException("a", "AbortError"))))) as typeof fetch;
    const err = await apiFetch("/x", { method: "POST" }, 5).catch((e) => e);
    globalThis.fetch = orig;
    expect(err.message).toBe(MIGHT_HAVE_SAVED);
  });
});
