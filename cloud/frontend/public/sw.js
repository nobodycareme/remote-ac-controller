// Minimal PWA service worker: cache app shell, network-first for navigation.
const CACHE = 'remote-ac-shell-v1';
const SHELL = ['./', './index.html', './icon.svg', './manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  // Never cache API; always go to network.
  if (req.url.includes('/api/')) {
    e.respondWith(fetch(req).catch(() => new Response('{"error":"offline"}', { status: 503, headers: { 'content-type': 'application/json' } })));
    return;
  }
  e.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req).then((res) => {
        if (res && res.status === 200 && (res.type === 'basic' || res.type === 'default')) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      });
      return cached || network;
    })
  );
});
