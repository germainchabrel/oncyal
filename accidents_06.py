"""
Points noirs : accidents corporels impliquant un vélo (ou un vélo à assistance électrique), 2020 à 2024,
dans les Alpes-Maritimes. Ajoute à out/reseau_06.csv.gz une colonne « acc_velo » (nombre d'accidents rattachés
au bout de rue le plus proche, à moins de 25 m).
Source : ONISR, bases de données annuelles des accidents corporels de la circulation routière (data.gouv.fr,
Licence Ouverte). Fichiers « caractéristiques » (date, lieu, coordonnées) et « véhicules » (catégorie :
1 = bicyclette, 80 = vélo à assistance électrique), dans data/accidents.
Lancer :  python accidents_06.py      (avant decoupe_06.py)
"""
import glob, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
VELOS = {1, 80}
MAX_M = 25.0
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def lire(motif):
    out = []
    for f in sorted(glob.glob("data/accidents/" + motif)):
        try:
            d = pd.read_csv(f, sep=";", dtype=str, encoding="utf-8")
        except UnicodeDecodeError:
            d = pd.read_csv(f, sep=";", dtype=str, encoding="latin-1")
        d.columns = [c.strip().strip('"').replace("﻿", "") for c in d.columns]
        if "Accident_Id" in d.columns:
            d = d.rename(columns={"Accident_Id": "Num_Acc"})
        out.append(d)
    return pd.concat(out, ignore_index=True)


def main():
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    t0 = time.time()
    car = lire("ca*.csv")            # caract-, caracteristiques-, carcteristiques- (orthographe officielle des fichiers 2021-2022)
    veh = lire("vehicules-*.csv")
    car = car[car["dep"].str.strip().str.lstrip("0").isin(["6"])]
    veh["catv"] = pd.to_numeric(veh["catv"], errors="coerce")
    velo = set(veh.loc[veh["catv"].isin(VELOS), "Num_Acc"])
    a = car[car["Num_Acc"].isin(velo)].copy()
    a["lat"] = pd.to_numeric(a["lat"].str.replace(",", "."), errors="coerce")
    a["lon"] = pd.to_numeric(a["long"].str.replace(",", "."), errors="coerce")
    a = a[(a.lat > 43.3) & (a.lat < 44.5) & (a.lon > 6.5) & (a.lon < 7.8)]
    log("accidents corporels avec un vélo dans le 06 (2020-2024) :", len(a), "géolocalisés")
    for an, n in a.groupby("an").size().items():
        log(f"   {an} : {n}")

    e = pd.read_csv(FICHIER)
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    ax, ay = map(np.asarray, tr.transform(e.alon.values, e.alat.values))
    bx, by = map(np.asarray, tr.transform(e.blon.values, e.blat.values))
    px, py = map(np.asarray, tr.transform(a.lon.values, a.lat.values))
    # bouts de rue proches de chaque accident (milieux à moins de 300 m), puis distance exacte au segment
    arbre = cKDTree(np.c_[(ax + bx) / 2, (ay + by) / 2])
    compte = np.zeros(len(e), np.int32)
    rattaches = 0
    for x, y in zip(px, py):
        cand = arbre.query_ball_point([x, y], 300)
        if not cand:
            continue
        c = np.array(cand)
        dx, dy = bx[c] - ax[c], by[c] - ay[c]
        l2 = dx * dx + dy * dy
        t = np.clip(np.where(l2 > 0, ((x - ax[c]) * dx + (y - ay[c]) * dy) / np.where(l2 > 0, l2, 1), 0), 0, 1)
        d = np.hypot(x - ax[c] - t * dx, y - ay[c] - t * dy)
        k = int(np.argmin(d))
        if d[k] <= MAX_M:
            compte[c[k]] += 1; rattaches += 1
    e["acc_velo"] = compte
    log("rattachés à une rue :", rattaches, "| bouts de rue concernés :", int((compte > 0).sum()), "| au moins 2 accidents :", int((compte >= 2).sum()))
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    log(f"écrit : {FICHIER} en {time.time() - t0:.0f} s")
    open("out/rapport_accidents_06.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
