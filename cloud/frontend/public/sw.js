// PWA service worker — network-first for the app shell so new deploys always
// propagate to returning visitors; cache is only an OFFLINE fallback.
// Cache version is bumped on every meaningful deploy to purge stale shells.
const CACHE = 'remote-ac-shell-v2';
const SHELL = ['./', './index.html', './icon.svg', './manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  // API traffic: never cache, always network.
  if (req.url.includes('/api/')) {
    e.respondWith(
      fetch(req).catch(() =>
        new Response('{"ok":false,"errorCode":"OFFLINE","message":"离线"}', {
          status: 503,
          headers: { 'content-type': 'application/json' },
        })
      )
    );
    return;
  }

  // Navigation (HTML document): NETWORK-FIRST. Always try the network so a new
  // index.html (and its freshly-hashed assets) is served; fall back to cache
  // only when the network is unreachable (true offline mode).
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match('./index.html')))
    );
    return;
  }

  // Static assets (hashed JS/CSS/icons): network-first, cache as offline fallback.
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && (res.type === 'basic' || res.type === 'default')) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
