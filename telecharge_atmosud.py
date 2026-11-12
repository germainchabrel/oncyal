import os, json, time
from io import BytesIO
import numpy as np, requests, tifffile
from pyproj import Transformer

BASE = "https://geoservices.atmosud.org/geoserver/mod_sudpaca_2024/wcs"
COUCHES = ["no2_moyan", "pm10_moyan", "pm25_moyan", "icair365"]
GX0, GY1, PAS = 795487.5, 6454512.5, 25.0      # coin haut-gauche de la grille AtmoSud
NX, NY = 11521, 9841                            # nombre de cases de la grille entière
BLOC = 1000                                     # cases par morceau (25 km)

# Rectangle des Alpes-Maritimes, converti en Lambert-93
tr = Transformer.from_crs(4326, 2154, always_xy=True)
pts = [tr.transform(lon, lat) for lon in (6.60, 7.75) for lat in (43.45, 44.40)]
xmin, xmax = min(p[0] for p in pts), max(p[0] for p in pts)
ymin, ymax = min(p[1] for p in pts), max(p[1] for p in pts)
c0 = max(0, int((xmin - GX0) // PAS)); c1 = min(NX, int(-(-(xmax - GX0) // PAS)))
r0 = max(0, int((GY1 - ymax) // PAS)); r1 = min(NY, int(-(-(GY1 - ymin) // PAS)))
print("zone :", r1 - r0, "x", c1 - c0, "cases")

os.makedirs("data/atmosud", exist_ok=True)
for nom in COUCHES:
    cid = f"mod_sudpaca_2024__mod_sudpaca_2024_{nom}"
    arr = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
    t0 = time.time()
    for rb in range(r0, r1, BLOC):
        re_ = min(rb + BLOC, r1)
        for cb in range(c0, c1, BLOC):
            ce = min(cb + BLOC, c1)
            xa, xb = GX0 + PAS * cb + 5, GX0 + PAS * ce - 5
            ya, yb = GY1 - PAS * re_ + 5, GY1 - PAS * rb - 5
            params = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"),
                      ("coverageId", cid), ("format", "image/tiff"),
                      ("subset", f"X({xa},{xb})"), ("subset", f"Y({ya},{yb})")]
            for essai in range(3):
                try:
                    r = requests.get(BASE, params=params, timeout=300)
                    r.raise_for_status()
                    break
                except Exception as e:
                    print("  nouvel essai :", e); time.sleep(5)
            else:
                raise SystemExit("échec de téléchargement")
            a = np.squeeze(tifffile.imread(BytesIO(r.content))).astype(np.float32)
            attendu = (re_ - rb, ce - cb)
            if a.shape != attendu:
                raise SystemExit(f"taille reçue {a.shape} au lieu de {attendu} (couche {nom}, morceau {rb},{cb})")
            a[a < -1e30] = np.nan
            arr[rb - r0:re_ - r0, cb - c0:ce - c0] = a
        print(f"  {nom} : ligne {rb}-{re_} faite")
    np.save(f"data/atmosud/{nom}.npy", arr)
    meta = dict(x0=GX0 + PAS * c0, y1=GY1 - PAS * r0, pas=PAS, lignes=r1 - r0, colonnes=c1 - c0, crs="EPSG:2154")
    json.dump(meta, open(f"data/atmosud/{nom}.json", "w"))
    v = arr[np.isfinite(arr)]
    print(f"{nom} : {100 * v.size / arr.size:.0f}% de cases valides, min {v.min():.1f}, moyenne {v.mean():.1f}, max {v.max():.1f}  ({time.time() - t0:.0f} s)")

# Contrôle : valeur au centre de Nice
x, y = tr.transform(7.262, 43.703)
arr = np.load("data/atmosud/no2_moyan.npy")
print("NO2 au centre de Nice :", arr[int((meta['y1'] - y) // PAS), int((x - meta['x0']) // PAS)])