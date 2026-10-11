// Minimal service worker — enables PWA installability.
// We're not caching anything aggressively because the app is dynamic.

self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

// Required for installability: a fetch handler, even if it just passes through.
self.addEventListener("fetch", (event) => {
    // Let the browser handle everything normally.
    // We're only here to satisfy the PWA install criteria.
});
