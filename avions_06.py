"""
Bruit des avions : ajoute au bruit des rues celui des aérodromes, d'après les plans d'exposition au bruit (PEB).
Source : DGAC, « Zonage des plans d'exposition au bruit (PEB) » (data.gouv.fr, Licence Ouverte), zones A à D,
dans data/avions (fichiers peb-za/zb/zc/zd.geojson). Dans le 06 : aéroport de Nice-Côte d'Azur et
aérodrome de Cannes-Mandelieu.
Le PEB est un document d'urbanisme qui délimite l'exposition au bruit à long terme. Ses zones correspondent à des
seuils de l'indicateur Lden : A au-delà de 70 dB, B jusqu'à 65 (ou 62), C jusqu'à 57 (ou 55), D jusqu'à 50.
Niveau retenu au milieu de chaque zone : A 72, B 67, C 60, D 53 dB. La nuit, le trafic aérien est bien plus faible :
niveau de nuit estimé à Lden - 12 dB.
Le bruit des avions s'additionne à celui des routes (somme énergétique : 10 log10(10^(a/10) + 10^(b/10))).
Colonnes : noise et noise_n (bruits combinés), noise_route et noise_n_route (bruits des routes seuls, gardés pour
pouvoir relancer ce script sans compter deux fois les avions), avion (0 aucune zone, 1 = D ... 4 = A).
Lancer :  python avions_06.py      (après nuit_06.py, avant decoupe_06.py)
"""
import json, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
BBOX = (6.55, 43.40, 7.80, 44.45)
NIVEAU = {"za": (4, 72.0), "zb": (3, 67.0), "zc": (2, 60.0), "zd": (1, 53.0)}
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def somme(a, b):
    return 10 * np.log10(10 ** (a / 10) + 10 ** (b / 10))


def main():
    import geopandas as gpd
    from shapely.geometry import box
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    t0 = time.time()
    zones = []
    for z, (code, db) in NIVEAU.items():
        f = f"data/avions/peb-{z}.geojson"
        if not os.path.exists(f):
            sys.exit(f + " introuvable")
        g = gpd.read_file(f, on_invalid="ignore").to_crs(4326)       # le fichier national contient quelques géométries invalides
        g = g[g.geometry.notna()].copy(); g["geometry"] = g.geometry.make_valid()
        g = g[g.intersects(box(*BBOX))]
        g["code"], g["db"] = code, db
        zones.append(g[["code", "db", "geometry"]])
        log(f"   zone {z[-1].upper()} : {len(g)} surface(s) dans le département")
    zones = gpd.GeoDataFrame(pd.concat(zones, ignore_index=True), crs=4326)

    e = pd.read_csv(FICHIER)
    if "noise_route" not in e:
        e["noise_route"], e["noise_n_route"] = e["noise"], e["noise_n"]
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy((e.alon + e.blon) / 2, (e.alat + e.blat) / 2), crs=4326)
    j = gpd.sjoin(pts, zones, how="inner", predicate="within").sort_values("code", ascending=False)
    j = j[~j.index.duplicated(keep="first")]
    code = np.zeros(len(e), np.int8); air = np.full(len(e), -np.inf)
    code[j.index.values] = j.code.values; air[j.index.values] = j.db.values
    route, route_n = e.noise_route.values.astype(float), e.noise_n_route.values.astype(float)
    e["noise"] = np.where(code > 0, somme(route, air), route).round(1)
    e["noise_n"] = np.where(code > 0, somme(route_n, air - 12), route_n).round(1)
    e["avion"] = code
    L = e.len_m.values
    for c, nom in ((4, "A"), (3, "B"), (2, "C"), (1, "D")):
        m = code == c
        log(f"   rues en zone {nom} : {L[m].sum() / 1000:.0f} km, hausse moyenne du bruit {np.mean(e.noise.values[m] - route[m]) if m.any() else 0:.1f} dB")
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    log(f"écrit : {FICHIER} en {time.time() - t0:.0f} s")
    open("out/rapport_avions_06.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
