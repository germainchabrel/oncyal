"""
Ajoute la lumière satellite NASA (VIIRS Black Marble, ~500 m) à out/reseau_06.csv.gz
Même source et même lecture que ton site : luminosité = (rouge + vert + bleu) / 765, de 0 (nuit noire) à 1.
Lancer :  python lumiere_06.py          (nécessite :  pip install pillow)
"""
import io, math, os, sys, time
import numpy as np
import pandas as pd
import requests
from PIL import Image

URL = ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/"
       "2016-01-01/GoogleMapsCompatible_Level8/8/{y}/{x}.png")
Z = 8
N = 2 ** Z
FICHIER = "out/reseau_06.csv.gz"
CACHE = "data/nasa"
os.makedirs(CACHE, exist_ok=True)
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def position_tuile(lon, lat):
    """Coordonnées (tuile x, tuile y, pixel x, pixel y) dans la grille Web Mercator niveau 8."""
    lat = np.clip(lat, -85.05, 85.05)
    fx = (lon + 180.0) / 360.0 * N
    fy = (1.0 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2.0 * N
    tx, ty = np.floor(fx).astype(int), np.floor(fy).astype(int)
    px = np.clip(np.floor((fx - tx) * 256).astype(int), 0, 255)
    py = np.clip(np.floor((fy - ty) * 256).astype(int), 0, 255)
    return tx, ty, px, py


def luminosite_tuile(x, y):
    """Tableau 256x256 de luminosité (0-1), ou None si la tuile n'existe pas."""
    chemin = f"{CACHE}/{Z}_{x}_{y}.png"
    if not os.path.exists(chemin):
        for essai in range(3):
            try:
                r = requests.get(URL.format(x=x, y=y), timeout=60)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                open(chemin, "wb").write(r.content)
                break
            except Exception as e:
                log("   nouvel essai tuile", x, y, ":", e)
                time.sleep(3)
        else:
            raise SystemExit(f"échec de téléchargement de la tuile {x}/{y}")
    im = np.asarray(Image.open(chemin).convert("RGBA"), dtype=np.float32)
    return (im[:, :, 0] + im[:, :, 1] + im[:, :, 2]) / 765.0


def lumiere_aux_points(lon, lat):
    tx, ty, px, py = position_tuile(lon, lat)
    res = np.full(len(lon), np.nan, dtype=np.float32)
    cles = pd.Series(tx * 100000 + ty)
    for cle in cles.unique():
        m = (cles == cle).values
        x, y = int(cle // 100000), int(cle % 100000)
        t = luminosite_tuile(x, y)
        if t is None:
            log("   tuile sans donnée :", x, y)
            continue
        res[m] = t[py[m], px[m]]
    return res


def main():
    if not os.path.exists(FICHIER):
        sys.exit(f"{FICHIER} introuvable : lance d'abord prepare_06.py")
    e = pd.read_csv(FICHIER)
    log("réseau lu :", len(e), "bouts de rue")
    lon = ((e.alon + e.blon) / 2).values
    lat = ((e.alat + e.blat) / 2).values
    e["lum_nasa"] = lumiere_aux_points(lon, lat).round(3)

    v = e.lum_nasa
    log("part avec lumière satellite valide :", f"{100 * v.notna().mean():.0f} %")
    log("luminosité NASA : min", round(v.min(), 3), "| médiane", round(v.median(), 3), "| max", round(v.max(), 3))
    log("\nluminosité moyenne selon l'éclairage OSM (lit : 1 = éclairé, 0 = non, -1 = inconnu) :")
    log(e.groupby("lit").agg(n=("a", "size"), lum_nasa=("lum_nasa", "mean")).round(3).to_string())
    log("\nrépartition des valeurs (percentiles 5 / 25 / 50 / 75 / 95 / 99) :",
        np.nanpercentile(v, [5, 25, 50, 75, 95, 99]).round(3))

    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    log(f"\nécrit : {FICHIER} ({os.path.getsize(FICHIER) // 1_000_000} Mo)")
    open("out/rapport_lumiere_06.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
