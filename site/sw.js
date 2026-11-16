/* Oncyal : mode hors ligne.
   - la page, les icônes et la bibliothèque de carte sont gardées dès la première visite ;
   - les zones de données (tuiles/*.bin) sont gardées au fur et à mesure qu'elles sont consultées ;
   - la page est d'abord demandée au réseau (pour les mises à jour), puis lue en cache si le réseau manque ;
   - le fond de carte OpenStreetMap et les services de recherche ne sont pas mis en cache (politique d'usage d'OSM).
   VERSION change à chaque régénération des données (mise_a_jour_06.py) : l'ancien cache est alors supprimé. */
var VERSION = 'oncyal-2026-11-16-1958';
var LEAFLET = ['https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css', 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
  'https://cdn.jsdelivr.net/npm/opening_hours@3.15.0/build/opening_hours.min.js'];
var COQUILLE = ['./', 'index.html', 'manifest.webmanifest', 'favicon.svg', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png',
  'tuiles/index.json', 'tuiles/hw.json'].concat(LEAFLET);

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(COQUILLE); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
function enCache(req, rep) { if (rep && rep.ok) { var copie = rep.clone(); caches.open(VERSION).then(function (c) { c.put(req, copie); }); } return rep; }
self.addEventListener('fetch', function (e) {
  var req = e.request, u = new URL(req.url);
  if (req.method !== 'GET') return;
  var local = u.origin === self.location.origin;
  if ((local && /\/tuiles\/.+\.bin$/.test(u.pathname)) || LEAFLET.indexOf(req.url) >= 0) {
    // données et bibliothèque : le cache d'abord (elles ne changent qu'avec une nouvelle VERSION)
    e.respondWith(caches.match(req).then(function (r) { return r || fetch(req).then(function (rep) { return enCache(req, rep); }); }));
  } else if (local) {
    // page, index, icônes : le réseau d'abord, le cache si hors ligne
    e.respondWith(fetch(req).then(function (rep) { return enCache(req, rep); }).catch(function () {
      return caches.match(req, { ignoreSearch: true }).then(function (r) { return r || caches.match('index.html'); });
    }));
  }
});
