// Cadence service worker: app shell + data cache for offline/flaky networks, and coach notifications.
//
// Caching rules (kept deliberately conservative so a deploy never serves stale JavaScript):
//  - Navigations are network-first; the last good index.html is the offline fallback. index.html names the
//    content-hashed bundles, so a fresh load always references fresh assets.
//  - /assets/* files are content-hashed and immutable: cache-first.
//  - GET /api/* is stale-while-revalidate: the network is raced against a short timeout and a cached copy is
//    served if the network is slow or down. Never cached: non-GET, /api/push, /api/share, /pair, requests
//    carrying Authorization, and responses marked no-store.
importScripts("/sw-logic.js");
const L = self.CadenceSW;
const VERSION = "v2";
const SHELL = `cadence-shell-${VERSION}`;
const ASSETS = `cadence-assets-${VERSION}`;
const DATA = `cadence-data-${VERSION}`;
const KEEP = [SHELL, ASSETS, DATA];
const SHELL_KEY = "/__shell";
const NEVER_CACHE = [/^\/api\/push(\/|$)/, /^\/api\/share(\/|$)/, /^\/pair(\/|$)/, /^\/api\/garmin\/sync/];
const SLOW_MS = 3500;
const FRESH_TIMEOUT_MS = 15000;
const MAX_ASSETS = 200;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(L.staleCaches(names, KEEP).map((n) => caches.delete(n))))
      .then(pruneAssets)
      .then(() => self.clients.claim()),
  ),
);

const cacheable = (res) => res && res.ok && res.type !== "opaque" && !/no-store/i.test(res.headers.get("Cache-Control") || "");
const clearData = () => caches.delete(DATA).catch(() => {});
async function pruneAssets() {
  const cache = await caches.open(ASSETS);
  const keys = await cache.keys();
  await Promise.all(L.pruneKeys(keys, MAX_ASSETS).map((k) => cache.delete(k)));
}
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "clear-cache") event.waitUntil(clearData());
});
const put = (name, key, res) => caches.open(name).then((c) => c.put(key, res)).catch(() => {});

async function navigate(request) {
  try {
    const res = await fetch(request);
    if (cacheable(res) && (res.headers.get("Content-Type") || "").includes("text/html")) put(SHELL, SHELL_KEY, res.clone());
    return res;
  } catch (err) {
    const cached = await caches.match(SHELL_KEY, { cacheName: SHELL });
    if (cached) return cached;
    throw err;
  }
}

async function hashedAsset(request) {
  const cached = await caches.match(request, { cacheName: ASSETS });
  if (cached) return cached;
  const res = await fetch(request);
  if (L.assetCacheable(res)) put(ASSETS, request, res.clone());
  return res;
}

async function apiData(event) {
  const request = event.request;
  const cached = await caches.match(request, { cacheName: DATA });
  const fresh = L.wantsFresh(request.headers);
  const network = fetch(request).then((res) => {
    if (L.isAuthFailure(res.status)) clearData();
    else if (cacheable(res)) put(DATA, request, res.clone());
    return res;
  });
  if (!cached) return network;
  network.catch(() => {});
  event.waitUntil(network.catch(() => {}));
  // The server's verdict wins: an auth failure or (for fresh requests) any answer is never replaced by the cache.
  const usable = (res) => res.status >= 500 && !L.isAuthFailure(res.status);
  if (fresh) {
    // After a write the cached copy predates it: wait for the network, fall back only if it fails or is very slow.
    const slow = new Promise((resolve) => setTimeout(() => resolve(cached), FRESH_TIMEOUT_MS));
    return Promise.race([network.then((res) => (usable(res) ? cached : res), () => cached), slow]);
  }
  const slow = new Promise((resolve) => setTimeout(() => resolve(cached), SLOW_MS));
  return Promise.race([network.then((res) => (usable(res) ? cached : res), () => cached), slow]);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || request.headers.has("Authorization")) return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === "navigate" && L.clearsOnNavigate(url.pathname)) event.waitUntil(clearData());
  if (NEVER_CACHE.some((re) => re.test(url.pathname))) return;
  if (request.mode === "navigate") return event.respondWith(navigate(request));
  if (url.pathname.startsWith("/assets/")) return event.respondWith(hashedAsset(request));
  if (url.pathname.startsWith("/api/")) return event.respondWith(apiData(event));
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Cadence", {
      body: data.body || "",
      tag: data.tag || undefined,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          // navigate() rejects for uncontrolled clients (notably iOS); fall back to opening a window.
          return client
            .navigate(url)
            .then((c) => (c || client).focus())
            .catch(() => self.clients.openWindow(url));
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
