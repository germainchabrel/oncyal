"""
Ombre : pour chaque bout de rue, de quoi savoir s'il est à l'ombre à une heure donnée.
Ajoute à out/reseau_06.csv.gz trois colonnes :
  omb_g, omb_d : rapport hauteur / distance du bâtiment le plus « couvrant » à gauche et à droite de la rue
                 (gauche et droite dans le sens a -> b), cherché à moins de 40 m du milieu du bout de rue ;
  arbres       : 1 si un arbre ou un alignement d'arbres est recensé à moins de 8 m.
La page calcule ensuite l'ombre elle-même : le soleil étant du côté gauche (ou droit) de la rue, à la hauteur h
au-dessus de l'horizon et faisant un angle a avec l'axe de la rue, le milieu de la rue est à l'ombre si
  rapport x |sin a| / tan h >= 1.
Source : bâtiments et arbres d'OpenStreetMap. La hauteur vient de l'étiquette height, sinon du nombre d'étages
(3 m par étage + 1 m), sinon d'une valeur type selon le genre de bâtiment : c'est une estimation.
Lancer :  python ombre_06.py      (avant decoupe_06.py)
"""
import glob, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
PBF = sorted(glob.glob("data/**/*.pbf", recursive=True))[0]
BBOX = (6.55, 43.40, 7.80, 44.45)
RAYON = 40.0
TYPE_H = {"house": 6, "detached": 6, "semidetached_house": 6, "bungalow": 4, "garage": 3, "garages": 3, "shed": 3, "hut": 3,
          "roof": 4, "greenhouse": 3, "apartments": 15, "residential": 12, "commercial": 10, "retail": 7, "industrial": 8,
          "warehouse": 8, "church": 16, "cathedral": 25, "chapel": 8, "hotel": 18, "office": 15, "school": 9, "hospital": 15}


def hauteur(t):
    h = t.get("height")
    if h:
        try:
            return float(h.replace("m", "").replace(",", ".").strip())
        except ValueError:
            pass
    n = t.get("building:levels")
    if n:
        try:
            return float(n.replace(",", ".")) * 3 + 1
        except ValueError:
            pass
    return float(TYPE_H.get(t.get("building"), 9))


def main():
    import osmium, shapely
    from shapely import STRtree
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    t0 = time.time()
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    lo0, la0, lo1, la1 = BBOX
    coords, tailles, hs, arbres = [], [], [], []
    fp = osmium.FileProcessor(PBF).with_locations().with_filter(osmium.filter.KeyFilter("building", "natural"))
    for o in fp:
        if o.is_node():
            if o.tags.get("natural") == "tree" and lo0 <= o.location.lon <= lo1 and la0 <= o.location.lat <= la1:
                arbres.append((o.location.lon, o.location.lat))
            continue
        if not o.is_way():
            continue
        try:
            c = [(n.lon, n.lat) for n in o.nodes]
        except Exception:
            continue
        if not c or not (lo0 <= c[0][0] <= lo1 and la0 <= c[0][1] <= la1):
            continue
        if o.tags.get("natural") == "tree_row":
            for i in range(len(c) - 1):                       # un point tous les ~8 m le long de l'alignement
                k = max(1, int(np.hypot((c[i + 1][0] - c[i][0]) * 80000, (c[i + 1][1] - c[i][1]) * 111000) / 8))
                for j in range(k + 1):
                    arbres.append((c[i][0] + (c[i + 1][0] - c[i][0]) * j / k, c[i][1] + (c[i + 1][1] - c[i][1]) * j / k))
            continue
        b = o.tags.get("building")
        if not b or b == "no" or len(c) < 4 or c[0] != c[-1]:
            continue
        t = {x.k: x.v for x in o.tags}
        coords.extend(c); tailles.append(len(c)); hs.append(hauteur(t))
    print(len(tailles), "bâtiments,", len(arbres), "points d'arbres")
    xy = np.c_[tr.transform(*np.array(coords).T)]
    fins = np.cumsum(tailles); debuts = fins - tailles
    polys = shapely.polygons(shapely.linearrings(xy, indices=np.repeat(np.arange(len(tailles)), tailles)))
    ok = shapely.is_valid(polys)
    polys, hs = polys[ok], np.array(hs)[ok]
    arbre = STRtree(polys)

    e = pd.read_csv(FICHIER)
    ax, ay = map(np.asarray, tr.transform(e.alon.values, e.alat.values))
    bx, by = map(np.asarray, tr.transform(e.blon.values, e.blat.values))
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    M = len(e)
    g, d = np.zeros(M), np.zeros(M)
    PAS = 150000
    for s in range(0, M, PAS):
        f = min(M, s + PAS)
        pts = shapely.points(mx[s:f], my[s:f])
        ie, ib = arbre.query(pts, predicate="dwithin", distance=RAYON)
        if not len(ie):
            continue
        lignes = shapely.shortest_line(pts[ie], polys[ib])
        c = shapely.get_coordinates(lignes).reshape(-1, 2, 2)
        vx, vy = c[:, 1, 0] - c[:, 0, 0], c[:, 1, 1] - c[:, 0, 1]
        dist = np.hypot(vx, vy)
        rap = hs[ib] / np.maximum(dist, 2.0)
        cote = dx[s + ie] * vy - dy[s + ie] * vx              # > 0 : bâtiment à gauche du sens a -> b
        dedans = dist < 0.05                                   # passage sous un bâtiment : ombre des deux côtés
        np.maximum.at(g, s + ie[(cote > 0) | dedans], rap[(cote > 0) | dedans])
        np.maximum.at(d, s + ie[(cote < 0) | dedans], rap[(cote < 0) | dedans])
        print(f"   {f}/{M} bouts de rue", flush=True)
    e["omb_g"], e["omb_d"] = np.round(np.minimum(g, 25), 1), np.round(np.minimum(d, 25), 1)
    arb = np.zeros(M, np.int8)
    if arbres:
        txy = np.c_[tr.transform(*np.array(arbres).T)]
        kd = cKDTree(txy)
        for fr in (0.0, 0.5, 1.0):
            dd, _ = kd.query(np.c_[ax + fr * dx, ay + fr * dy], distance_upper_bound=8)
            arb |= np.isfinite(dd)
    e["arbres"] = arb
    L = e.len_m.values
    print(f"rues bordées d'un bâtiment à moins de {RAYON:.0f} m : {100 * L[(g > 0) | (d > 0)].sum() / L.sum():.0f} % de la longueur ; arbres : {100 * L[arb > 0].sum() / L.sum():.1f} %")
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    print(f"écrit : {FICHIER} en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
