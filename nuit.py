"""
Bruit de nuit : ajoute au réseau du département (out/dep/<code>/reseau.csv.gz) une colonne « noise_n » (dB, indicateur Lnight, 22 h - 6 h).

La nuit, le trafic baisse et le bruit n'est pas celui de la journée : un trajet de nuit doit être calculé sur le
bruit de nuit. Source : cartes de bruit stratégiques 2022 du Cerema, indicateur Lnight (type A, routes et voies ferrées),
dans le même dossier que les cartes Lden utilisées le jour.
  - rue couverte par une carte Lnight : milieu de la tranche (50-55 dB -> 52,5 dB) ;
  - rue couverte de jour (Lden officiel) mais pas de nuit : bruit de nuit sous 50 dB, estimé à min(Lden - 8, 47,5) ;
  - ailleurs (bruit estimé de jour) : Lden estimé - 8 dB, écart moyen entre jour et nuit pour le trafic routier.
Lancer :  python nuit.py      (après bruit_complement.py)
"""
import glob, os, sys, time
import numpy as np
import pandas as pd

import config

FICHIER = config.FICHIER
PAS = 25.0
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def main():
    import geopandas as gpd
    from pyproj import Transformer
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    t0 = time.time()
    e = pd.read_csv(FICHIER)
    log("réseau lu :", len(e), "bouts de rue")
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    ax, ay = map(np.asarray, tr.transform(e.alon.values, e.alat.values))
    bx, by = map(np.asarray, tr.transform(e.blon.values, e.blat.values))
    L = np.hypot(bx - ax, by - ay)
    n = np.clip(np.ceil(L / PAS), 1, 400).astype(np.int64)
    idx = np.repeat(np.arange(len(L)), n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    t = (k + 0.5) / n[idx]
    px, py = ax[idx] + t * (bx - ax)[idx], ay[idx] + t * (by - ay)[idx]
    log("   ", len(px), "points d'échantillon")

    polys = []
    for motif in (f"*R_A_LN_S_{config.DEP3}.shp", f"*F_A_LN_S_{config.DEP3}.shp"):
        for f in glob.glob("data/cerema/**/" + motif, recursive=True):
            g = config.zones_bruit(f)
            if g is None or not len(g):
                continue
            polys.append(g)
            log("   ", os.path.basename(f), ":", len(g), "zones")
    res = np.full(len(px), np.nan)
    pas = 400_000
    if polys:
        polys = gpd.GeoDataFrame(pd.concat(polys, ignore_index=True), crs=2154)
    else:
        log("    aucune carte Lnight du Cerema pour ce département : bruit de nuit entièrement estimé")
    for d in range(0, len(px) if len(polys) else 0, pas):
        pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(px[d:d + pas], py[d:d + pas]), crs=2154)
        j = gpd.sjoin(pts, polys, how="inner", predicate="within")
        if len(j):
            s = j.groupby(level=0)["lvl"].max()
            res[d + s.index.values] = s.values + 2.5
        log(f"    nuit : {min(d + pas, len(px))}/{len(px)} points")
    ok = np.isfinite(res)
    somme = np.bincount(idx[ok], weights=res[ok], minlength=len(e))
    nb = np.bincount(idx[ok], minlength=len(e))
    with np.errstate(invalid="ignore", divide="ignore"):
        ln_off = np.where(nb > 0, somme / nb, np.nan)

    lden, off_jour = e.noise.values.astype(float), e.noise_src.values == 1
    ln = np.where(np.isfinite(ln_off), ln_off, np.where(off_jour, np.minimum(lden - 8, 47.5), lden - 8))
    e["noise_n"] = np.round(ln, 1)
    log("\n   bruit de nuit officiel :", f"{100 * np.isfinite(ln_off).mean():.0f} % des bouts de rue")
    log("   écart moyen jour - nuit :", f"{np.nanmean(lden - ln):.1f} dB")
    log("   part des rues au-dessus de 62 dB la nuit (seuil des points noirs) :", f"{100 * (ln >= 62).mean():.1f} %")
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    log(f"\nécrit : {FICHIER} en {time.time() - t0:.0f} s")
    open(f"{config.DOSSIER}/rapport_nuit.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
