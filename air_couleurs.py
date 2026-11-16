"""
Air : cartes annuelles de NO2 que les agences ne publient qu'en image. Les valeurs sont retrouvées d'après les couleurs.

Toutes ces cartes utilisent la palette commune des agences de surveillance de l'air (du bleu-vert au rouge sombre),
soit en classes de 1,6 µg/m3 (Atmo Grand Est, Atmo Hauts-de-France), soit en dégradé continu entre les mêmes
couleurs (Air Breizh, Lig'Air, Atmo Occitanie, Qualitair Corse). Chaque couleur de la palette vaut le milieu de sa
classe ; une couleur intermédiaire est placée sur le segment de palette le plus proche (interpolation).
Précision : environ 1 µg/m3. Limite : en dessous de 9,6 µg/m3 la palette n'a qu'une seule couleur ; ces cases
reçoivent 6 µg/m3 (air peu pollué, sans distinction plus fine).

Trois façons de récupérer l'image d'un département, toujours ramenée à une grille Lambert-93 de 25 m :
  export   serveur ArcGIS dynamique (opération « export », PNG sans perte)          Atmo Hauts-de-France
  tuiles   tuiles en cache d'un serveur ArcGIS (Web Mercator)                         Atmo Grand Est, Atmo Occitanie, Qualitair Corse
  wms      service WMS (GetMap, PNG sans perte)                                       Air Breizh, Lig'Air
Occitanie : la seule carte régionale de NO2 publiée date de 2017 ; les agglomérations de Toulouse, Montpellier,
Nîmes et Perpignan ont une carte 2025. La carte 2017 est ramenée au niveau de 2025 (rapport médian mesuré là où
les deux cartes se recouvrent), puis les cartes 2025 sont posées par-dessus.
Résultat : data/air/<code>/no2_moyan.npy et .json, comme pour les autres agences (voir telecharge.py).
"""
import io, json, math, os, sys, time
import numpy as np
import requests

UA = {"User-Agent": "Mozilla/5.0"}
PAS = 25.0
# couleur de la palette -> NO2 au milieu de la classe (µg/m3)
PALETTE = [((0, 204, 170), 8.8), ((31, 209, 135), 10.45), ((62, 214, 103), 12.05), ((91, 219, 68), 13.65), ((123, 224, 34), 15.25),
           ((153, 230, 0), 16.85), ((172, 235, 0), 18.45), ((192, 240, 0), 20.05), ((212, 245, 0), 21.65), ((233, 250, 0), 23.25),
           ((255, 255, 0), 24.85), ((255, 238, 0), 26.45), ((255, 221, 0), 28.05), ((255, 204, 0), 29.65), ((255, 187, 0), 31.25),
           ((255, 170, 0), 32.85), ((255, 136, 0), 34.45), ((255, 102, 0), 36.05), ((255, 68, 0), 37.65), ((255, 34, 0), 39.25),
           ((255, 0, 0), 44.0), ((230, 0, 0), 52.0), ((204, 0, 0), 60.0), ((179, 0, 0), 68.0), ((153, 0, 0), 76.0), ((128, 0, 0), 90.0)]
BAS = 6.0                 # valeur donnée à la première couleur (toutes les classes sous 9,6 µg/m3)
ECART_MAX = 45.0          # distance de couleur au-delà de laquelle une case n'appartient pas à la carte (fond, texte)


def http(url, essais=6, **kw):
    kw.setdefault("headers", UA); kw.setdefault("timeout", 180)
    for i in range(essais):
        try:
            r = requests.get(url, **kw)
            if r.status_code == 404:
                return None
            r.raise_for_status(); return r
        except Exception as ex:
            if i == essais - 1:
                raise
            time.sleep(10 * (i + 1))


def decoder(rgba):
    """Image RGBA (h, w, 4) -> NO2 (h, w) en float32, NaN hors de la carte."""
    h, w = rgba.shape[:2]
    p = rgba.reshape(-1, 4)
    ok = p[:, 3] >= 128
    cle = (p[:, 0].astype(np.uint32) << 16) | (p[:, 1].astype(np.uint32) << 8) | p[:, 2]
    u, inv = np.unique(cle[ok], return_inverse=True)
    c = np.stack([(u >> 16) & 255, (u >> 8) & 255, u & 255], 1).astype(np.float64)
    a = np.array([q[0] for q in PALETTE[:-1]], float); b = np.array([q[0] for q in PALETTE[1:]], float)
    va = np.array([q[1] for q in PALETTE[:-1]]); vb = np.array([q[1] for q in PALETTE[1:]])
    ab = b - a
    val = np.full(len(u), np.nan)
    for i0 in range(0, len(u), 200000):                        # par paquets : couleurs x segments de palette
        cc = c[i0:i0 + 200000]
        t = np.clip(((cc[:, None, :] - a[None]) * ab[None]).sum(2) / (ab * ab).sum(1)[None], 0, 1)
        d = np.sqrt(((cc[:, None, :] - (a[None] + t[..., None] * ab[None])) ** 2).sum(2))
        k = d.argmin(1); r = np.arange(len(cc))
        v = va[k] + t[r, k] * (vb[k] - va[k])
        v[d[r, k] > ECART_MAX] = np.nan
        v[np.abs(cc - np.array(PALETTE[0][0])).sum(1) <= 3] = BAS
        val[i0:i0 + 200000] = v
    out = np.full(h * w, np.nan, np.float32)
    out[ok] = val[inv]
    return out.reshape(h, w)


def image(octets):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    return np.asarray(Image.open(io.BytesIO(octets)).convert("RGBA"))


def grille(dep):
    """Grille de 25 m en Lambert-93 couvrant l'emprise du département : (x0, y1, largeur, hauteur)."""
    import config
    from pyproj import Transformer
    lo0, la0, lo1, la1 = config.bbox(dep)
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    pts = [tr.transform(lon, lat) for lon in (lo0, lo1) for lat in (la0, la1)]
    xmin, xmax, ymin, ymax = min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts)
    x0, y1 = math.floor(xmin / PAS) * PAS, math.ceil(ymax / PAS) * PAS
    return x0, y1, int(math.ceil((xmax - x0) / PAS)), int(math.ceil((y1 - ymin) / PAS))


def par_blocs(dep, bloc, demande):
    """Images demandées directement en Lambert-93 (export ArcGIS ou WMS), par blocs."""
    x0, y1, W, H = grille(dep)
    arr = np.full((H, W), np.nan, np.float32)
    for i in range(0, H, bloc):
        for j in range(0, W, bloc):
            h, w = min(bloc, H - i), min(bloc, W - j)
            r = demande((x0 + j * PAS, y1 - (i + h) * PAS, x0 + (j + w) * PAS, y1 - i * PAS), w, h)
            if r is None or not r.headers.get("Content-Type", "").startswith("image"):
                continue
            a = image(r.content)
            if a.shape[:2] == (h, w):
                arr[i:i + h, j:j + w] = decoder(a)
    return arr, x0, y1


def depuis_export(dep, c):
    return par_blocs(dep, 4000, lambda bb, w, h: http(c["export"] + "/export", params={
        "bbox": ",".join(str(v) for v in bb), "bboxSR": 2154, "imageSR": 2154, "size": f"{w},{h}", "dpi": 96, "format": "png32",
        "transparent": "true", "layers": f"show:{c['couche']}", "f": "image"}))


def depuis_wms(dep, c):
    return par_blocs(dep, 2000, lambda bb, w, h: http(c["wms"], params={
        "service": "WMS", "version": "1.1.1", "request": "GetMap", "layers": c["couche"], "styles": "", "srs": "EPSG:2154",
        "bbox": ",".join(str(v) for v in bb), "width": w, "height": h, "format": "image/png", "transparent": "true"}))


def depuis_tuiles(dep, url, z):
    """Tuiles Web Mercator d'un serveur ArcGIS, assemblées puis rééchantillonnées (au plus proche) sur la grille Lambert-93."""
    from pyproj import Transformer
    x0, y1, W, H = grille(dep)
    T = 20037508.342789244
    res = 2 * T / (256 * 2 ** z)
    tr = Transformer.from_crs(2154, 3857, always_xy=True)
    cx, cy = tr.transform([x0, x0 + W * PAS, x0, x0 + W * PAS], [y1, y1, y1 - H * PAS, y1 - H * PAS])
    tx0, tx1 = int((min(cx) + T) // (256 * res)), int((max(cx) + T) // (256 * res))
    ty0, ty1 = int((T - max(cy)) // (256 * res)), int((T - min(cy)) // (256 * res))
    # la carte ne couvre peut-être pas ce département (carte d'agglomération) : son emprise est lue avant de demander les tuiles
    try:
        e = http(url, params={"f": "json"}).json().get("fullExtent") or {}
        if e and (e["xmax"] < min(cx) or e["xmin"] > max(cx) or e["ymax"] < min(cy) or e["ymin"] > max(cy)):
            return np.full((H, W), np.nan, np.float32), x0, y1, 0
    except Exception:
        pass
    mos = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 4), np.uint8)
    s = requests.Session()

    def une(t):
        ty, tx = t
        for essai in range(5):
            try:
                r = s.get(f"{url}/tile/{z}/{ty}/{tx}", headers=UA, timeout=120)
                if r.status_code != 200 or not r.content:
                    return None
                a = image(r.content)
                return (ty, tx, a) if a.shape[:2] == (256, 256) else None
            except Exception:
                time.sleep(5 * (essai + 1))
        return None

    from concurrent.futures import ThreadPoolExecutor
    n = 0
    with ThreadPoolExecutor(6) as ex:                           # six demandes à la fois : rapide sans bousculer le serveur
        for res_ in ex.map(une, [(ty, tx) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]):
            if res_:
                ty, tx, a = res_
                mos[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a; n += 1
    val = decoder(mos)
    del mos
    arr = np.full((H, W), np.nan, np.float32)
    xs = x0 + (np.arange(W) + 0.5) * PAS
    for i0 in range(0, H, 500):
        ys = y1 - (np.arange(i0, min(H, i0 + 500)) + 0.5) * PAS
        X, Y = np.meshgrid(xs, ys)
        mx, my = tr.transform(X.ravel(), Y.ravel())
        col = np.floor((np.asarray(mx) + T) / res).astype(np.int64) - tx0 * 256
        lig = np.floor((T - np.asarray(my)) / res).astype(np.int64) - ty0 * 256
        ok = (col >= 0) & (col < val.shape[1]) & (lig >= 0) & (lig < val.shape[0])
        v = np.full(col.shape, np.nan, np.float32)
        v[ok] = val[lig[ok], col[ok]]
        arr[i0:i0 + len(ys)] = v.reshape(len(ys), W)
    return arr, x0, y1, n


def telecharger(dep, nom, c):
    import config
    dos = config.air_dir(dep)
    if os.path.exists(f"{dos}/no2_moyan.npy"):
        return
    os.makedirs(dos, exist_ok=True)
    t0 = time.time()
    detail = ""
    if "export" in c:
        arr, x0, y1 = depuis_export(dep, c)
    elif "wms" in c:
        arr, x0, y1 = depuis_wms(dep, c)
    else:
        arr, x0, y1, n = depuis_tuiles(dep, c["tuiles"], c["z"])
        detail = f"{n} tuiles"
        if c.get("dessus"):                                   # cartes récentes d'agglomération posées sur la carte régionale ancienne
            recents = np.full(arr.shape, np.nan, np.float32)
            for url, z in c["dessus"]:
                a2 = depuis_tuiles(dep, url, z)[0]
                recents = np.where(np.isfinite(a2), a2, recents)
            deux = np.isfinite(recents) & np.isfinite(arr) & (arr > 9.6) & (recents > 9.6)
            rapport = float(np.median(recents[deux] / arr[deux])) if deux.sum() > 5000 else c.get("rapport", 1.0)
            arr = np.where(arr > 9.6, np.maximum(arr * rapport, BAS), arr)
            arr = np.where(np.isfinite(recents), recents, arr)
            detail += f", carte régionale {c['annee']} multipliée par {rapport:.2f}, {100 * np.isfinite(recents).mean():.0f} % de la grille en carte récente"
    np.save(f"{dos}/no2_moyan.npy", arr)
    json.dump(dict(x0=x0, y1=y1, pas=PAS, lignes=arr.shape[0], colonnes=arr.shape[1], crs="EPSG:2154", source=nom, methode="couleurs", annee=c.get("annee")), open(f"{dos}/no2_moyan.json", "w"))
    v = arr[np.isfinite(arr)]
    if not len(v):
        print(f"air {nom} {dep} : aucune case lue (carte vide ?)", flush=True); return
    print(f"air {nom} {dep} (couleurs) : {arr.shape[0]} x {arr.shape[1]} cases de 25 m, {100 * v.size / arr.size:.0f} % valides, NO2 moyen {v.mean():.1f}, "
          f"centile 99 {np.percentile(v, 99):.0f}, max {v.max():.0f} {('(' + detail + ') ') if detail else ''}({time.time() - t0:.0f} s)", flush=True)
