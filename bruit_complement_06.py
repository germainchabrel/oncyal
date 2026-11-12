"""
Complète le bruit pour les voies que les cartes du Cerema ne couvrent pas (autoroutes à péage comme l'A8,
routes de moins de 8 200 véhicules/jour...). Pour chaque bout de rue SANS bruit officiel, on estime le bruit
d'après les routes importantes voisines non couvertes : niveau au bord de la voie - 13 x log10(distance / 10 m),
jusqu'à 250 m (même modèle que ton site). Les bouts de rue AVEC bruit officiel ne sont pas touchés.
Lancer :  python bruit_complement_06.py        (nécessite :  pip install scipy)
"""
import os, sys
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
PORTEE = 250.0
# classe de voie -> bruit au bord de la voie (dB), identique à prepare_06.py
SOURCES = {"motorway": 78, "trunk": 74, "primary": 70, "secondary": 66, "tertiary": 62,
           "motorway_link": 78, "trunk_link": 74, "primary_link": 70, "secondary_link": 66, "tertiary_link": 62}
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def modele_bruit(x, y, niveau_source, est_source):
    """x, y : positions (m). niveau_source : dB au bord de la voie (0 si pas une voie importante).
    est_source : True pour les bouts de rue qui servent de source (voies importantes SANS bruit officiel).
    Retourne le bruit estimé en chaque point (dB), -inf si aucune source à moins de PORTEE."""
    from scipy.spatial import cKDTree
    res = np.full(len(x), -np.inf)
    for niv in np.unique(niveau_source[est_source]):
        m = est_source & (niveau_source == niv)
        arbre = cKDTree(np.column_stack([x[m], y[m]]))
        d, _ = arbre.query(np.column_stack([x, y]), distance_upper_bound=PORTEE + 1e-6)
        ok = np.isfinite(d)
        niveau = niv - 13.0 * np.log10(np.maximum(d[ok], 10.0) / 10.0)
        res[ok] = np.maximum(res[ok], niveau)
    return res


def main():
    from pyproj import Transformer
    from prepare_06 import HW
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    e = pd.read_csv(FICHIER)
    log("réseau lu :", len(e), "bouts de rue")
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    x, y = tr.transform(((e.alon + e.blon) / 2).values, ((e.alat + e.blat) / 2).values)
    x, y = np.asarray(x), np.asarray(y)

    type_voie = np.array([HW[i] for i in e.hw.values])
    niv = np.array([SOURCES.get(t, 0) for t in type_voie], dtype=float)
    # Autoroutes : l'A8 n'est pas dans les cartes du Cerema. Un bout d'autoroute marqué "officiel" mais bas
    # (moins de 72,5 dB) se trouve dans la zone d'une route ou d'une voie ferrée voisine : cette valeur ne
    # représente pas le bruit de l'autoroute. On le repasse en estimation au niveau de son type (78 dB).
    faux = np.isin(type_voie, ["motorway", "motorway_link"]) & (e.noise_src.values == 1) & (e.noise.values < 72.5)
    log("autoroutes et bretelles 'officielles' trop basses, repassées en estimation :", int(faux.sum()))
    e.loc[faux, "noise"] = 78.0
    e.loc[faux, "noise_src"] = 0

    officiel = e.noise_src.values == 1
    source = (niv > 0) & ~officiel
    log("voies importantes sans bruit officiel (sources) :", int(source.sum()))

    avant = e.noise.values.copy()
    modele = modele_bruit(x, y, niv, source)
    nouveau = np.where(officiel, avant, np.maximum(avant, modele))
    e["noise"] = np.round(nouveau, 1)

    monte = (~officiel) & (nouveau > avant + 0.05)
    log("bouts de rue dont le bruit est relevé :", int(monte.sum()), f"({100 * monte.mean():.1f} %)")
    log("relèvement moyen sur ceux-là :", round(float((nouveau - avant)[monte].mean()), 1), "dB")
    piet = np.isin(type_voie, ["footway", "path", "pedestrian", "cycleway", "steps", "track"]) & monte
    log("dont chemins/trottoirs/pistes :", int(piet.sum()), "| relèvement moyen", round(float((nouveau - avant)[piet].mean()), 1) if piet.any() else 0, "dB")
    log("\nbruit moyen par type de voie (dB) après correction :")
    g = e.assign(type=type_voie).groupby("type").noise.agg(["mean", "size"]).round(1)
    log(g.loc[["motorway", "trunk", "primary", "secondary", "residential", "footway", "path"]].to_string())

    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    open("out/rapport_bruit_complement_06.txt", "w", encoding="utf-8").write("\n".join(rapport))
    log("\nécrit :", FICHIER)


if __name__ == "__main__":
    main()
