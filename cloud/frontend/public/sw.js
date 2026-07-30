// Legacy PWA cleanup worker. It unregisters itself and clears old CacheStorage
// entries so a prior release cannot keep serving stale HTML.
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((key) => caches.delete(key)));
      } catch {
        /* ignore */
      }
      try {
        await self.registration.unregister();
      } catch {
        /* ignore */
      }
      try {
        await self.clients.claim();
      } catch {
        /* ignore */
      }
    })()
  );
});
