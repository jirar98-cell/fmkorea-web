const SHELL_VER = 'v9';
const SHELL = `fmk-shell-${SHELL_VER}`;
const APIC  = `fmk-api-${SHELL_VER}`;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(['/'])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks =>
      Promise.all(ks.filter(k => k !== SHELL && k !== APIC).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request.clone())
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(APIC).then(c => c.put(e.request, clone));
          }
          return res;
        })
        .catch(() => caches.match(e.request).then(cached =>
          cached || new Response(
            JSON.stringify({ error: '오프라인 상태입니다. 캐시된 데이터를 불러올 수 없습니다.' }),
            { headers: { 'Content-Type': 'application/json; charset=utf-8' } }
          )
        ))
    );
    return;
  }

  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(() => caches.match('/')));
    return;
  }

  e.respondWith(caches.match(e.request).then(c => c || fetch(e.request)));
});

self.addEventListener('message', e => {
  if (e.data === 'skipWaiting') self.skipWaiting();
});
