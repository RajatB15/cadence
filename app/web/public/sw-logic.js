// Pure decisions for sw.js, kept free of service-worker globals so they can be unit tested.
// Loaded by sw.js through importScripts; also usable as a CommonJS module.
(function (root) {
  const logic = {
    /** The server refused this device: cached health data must go and never be served. */
    isAuthFailure: (status) => status === 401 || status === 403,
    /** Requests issued shortly after a write ask for the network, not the cached copy. */
    wantsFresh: (headers) => !!headers && headers.get("X-Cadence-Fresh") === "1",
    /** Only real, non-HTML, non-no-store responses are cached as hashed assets (SPA fallback returns HTML). */
    assetCacheable: (res) =>
      !!res && res.ok && res.type !== "opaque" && !/text\/html/i.test(res.headers.get("Content-Type") || "") && !/no-store/i.test(res.headers.get("Cache-Control") || ""),
    dataCacheable: (res) => !!res && res.ok && res.type !== "opaque" && !/no-store/i.test(res.headers.get("Cache-Control") || ""),
    /** Pairing page: a fresh pairing must start with no previous device's data. */
    clearsOnNavigate: (pathname) => /^\/pair(\/|$)/.test(pathname),
    /** Cache names to delete on activate: anything ours that is not current. */
    staleCaches: (names, keep) => names.filter((n) => n.startsWith("cadence-") && !keep.includes(n)),
    /** Cached asset requests that are not part of the current page set are pruned; keep the newest `max`. */
    pruneKeys: (keys, max) => (keys.length > max ? keys.slice(0, keys.length - max) : []),
  };
  if (typeof module !== "undefined" && module.exports) module.exports = logic;
  else root.CadenceSW = logic;
})(typeof self !== "undefined" ? self : this);
