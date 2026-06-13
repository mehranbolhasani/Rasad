const CACHE_VERSION = '__CACHE_VERSION__';
const CACHE_NAME = `rasad-v${CACHE_VERSION}`;

const APP_SHELL = [
  '/',
  '/manifest.json',
  '/style.css',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
];

const OFFLINE_FALLBACK = new Response(
  '<p style="font-family:sans-serif;direction:rtl;text-align:center;padding:2rem">اتصال به اینترنت برقرار نیست.</p>',
  {
    status: 503,
    statusText: 'Service Unavailable',
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  }
);

function isSameOrigin(request) {
  try {
    const url = new URL(request.url);
    return url.origin === self.location.origin;
  } catch (e) {
    return false;
  }
}

function normalizePath(request) {
  const url = new URL(request.url);
  return url.pathname;
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.map((key) => {
            if (key !== CACHE_NAME) {
              return caches.delete(key);
            }
          })
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;

  if (request.method !== 'GET') {
    return;
  }

  if (!isSameOrigin(request)) {
    return;
  }

  const path = normalizePath(request);

  if (path === '/' || path === '/index.html') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put('/', clone);
          });
          return response;
        })
        .catch(() => {
          return caches.match('/').then((cached) => {
            if (cached) {
              return cached;
            }
            return OFFLINE_FALLBACK;
          });
        })
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, clone);
          });
          return response;
        })
        .catch(() => {
          return new Response('', {
            status: 404,
            statusText: 'Not Found',
          });
        });
    })
  );
});
