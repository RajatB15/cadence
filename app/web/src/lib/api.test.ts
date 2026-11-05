import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, apiFetch, shouldRetry } from "./api";

const json = (body: unknown, init: ResponseInit = {}) => new Response(JSON.stringify(body), { status: 200, ...init });

beforeEach(() => vi.useRealTimers());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("request", () => {
  it("parses JSON and sets headers on writes", async () => {
    const f = vi.fn().mockResolvedValue(json({ delivered: 1 }));
    vi.stubGlobal("fetch", f);
    await expect(api.pushTest()).resolves.toEqual({ delivered: 1 });
    const init = f.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-Cadence-Request")).toBe("1");
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("sets JSON content type for string bodies but not FormData", async () => {
    const f = vi.fn().mockImplementation(() => Promise.resolve(json({})));
    vi.stubGlobal("fetch", f);
    await api.pushPrefs({ a: true });
    expect(new Headers((f.mock.calls[0][1] as RequestInit).headers).get("Content-Type")).toBe("application/json");
    await apiFetch("/api/x", { method: "POST", body: new FormData() });
    expect(new Headers((f.mock.calls[1][1] as RequestInit).headers).has("Content-Type")).toBe(false);
  });

  it("reports a non-JSON success body as a parse error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>oops</html>", { status: 200 })));
    await expect(api.push()).rejects.toMatchObject({ kind: "parse" });
  });

  it("uses statusText when an error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 502, statusText: "Bad Gateway" })));
    await expect(api.push()).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("surfaces the server detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Nope" }, { status: 409 })));
    await expect(api.push()).rejects.toMatchObject({ status: 409, message: "Nope" });
  });

  it("raises a distinct offline error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.push().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe("offline");
  });

  it("times out a hung request", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_p: string, init: RequestInit) => new Promise((_, reject) => {
        init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      })),
    );
    const p = apiFetch("/api/slow", {}, 1000).catch((e) => e);
    await vi.advanceTimersByTimeAsync(1001);
    const err = await p;
    expect(err.kind).toBe("timeout");
  });

  it("honours a caller abort", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_p: string, init: RequestInit) => new Promise((_, reject) => {
        init.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      })),
    );
    const ctrl = new AbortController();
    const p = apiFetch("/api/x", { signal: ctrl.signal }).catch((e) => e);
    ctrl.abort();
    expect((await p).kind).toBe("aborted");
  });
});

describe("shouldRetry", () => {
  it("skips 4xx and aborts, retries other failures once", () => {
    expect(shouldRetry(0, new ApiError(404, "x"))).toBe(false);
    expect(shouldRetry(0, new ApiError(0, "x", "aborted"))).toBe(false);
    expect(shouldRetry(0, new ApiError(503, "x"))).toBe(true);
    expect(shouldRetry(0, new ApiError(0, "x", "offline"))).toBe(true);
    expect(shouldRetry(1, new ApiError(503, "x"))).toBe(false);
  });
});
