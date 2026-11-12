"""
Lampadaires : une rue avec un lampadaire recensé dans OpenStreetMap (highway=street_lamp) à moins de 20 m est
comptée comme éclairée (colonne « lit » = 1), même si l'éclairage n'était pas renseigné sur la rue.
C'est une information à l'échelle de la rue, bien plus précise que l'image satellite (environ 500 m), mais très
inégale : environ 11 000 lampadaires recensés dans le 06, dont plus de 8 000 à Antibes.
Une rue explicitement déclarée non éclairée (lit=no) le reste.
Lancer :  python lampadaires_06.py      (avant decoupe_06.py)
"""
import glob, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
PBF = sorted(glob.glob("data/**/*.pbf", recursive=True))[0]
BBOX = (6.55, 43.40, 7.80, 44.45)


def main():
    import osmium
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    t0 = time.time()
    lamp = []
    fp = (osmium.FileProcessor(PBF).with_filter(osmium.filter.EntityFilter(osmium.osm.NODE))
          .with_filter(osmium.filter.KeyFilter("highway")))
    for n in fp:
        if n.tags.get("highway") == "street_lamp":
            x, y = n.location.lon, n.location.lat
            if BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3]:
                lamp.append((x, y))
    print(len(lamp), "lampadaires recensés")
    e = pd.read_csv(FICHIER)
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    lx, ly = map(np.asarray, tr.transform([p[0] for p in lamp], [p[1] for p in lamp]))
    ax, ay = map(np.asarray, tr.transform(e.alon.values, e.alat.values))
    bx, by = map(np.asarray, tr.transform(e.blon.values, e.blat.values))
    arbre = cKDTree(np.c_[lx, ly])
    proche = np.zeros(len(e), bool)
    for f in (0.0, 0.5, 1.0):                       # extrémités et milieu de chaque bout de rue
        d, _ = arbre.query(np.c_[ax + f * (bx - ax), ay + f * (by - ay)], distance_upper_bound=20)
        proche |= np.isfinite(d)
    avant = int((e.lit == 1).sum())
    e.loc[proche & (e.lit != 0), "lit"] = 1
    print(f"rues comptées éclairées : {avant} avant, {int((e.lit == 1).sum())} après")
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    print(f"écrit : {FICHIER} en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
