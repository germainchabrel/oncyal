"""
Air : (re)met dans le réseau d'un département la moyenne annuelle de NO2 de son agence régionale (colonne no2_moyan),
et l'indice annuel d'AtmoSud quand il existe (icair365). prepare.py le fait déjà quand la carte d'air est là au moment
du calcul ; ce script sert à rattraper un département traité sans air, ou à prendre une carte plus récente, sans
refaire tout le reste.

Lancer :  python air.py            (département : ONCYAL_DEP, voir config.py ; la carte est téléchargée si besoin)
Puis :    python assemble.py
"""
import os, sys, time
import numpy as np
import pandas as pd
import config
from prepare import AIR, AIR_DIR, echantillonner, lire_grille, moyenne_par_arete, valeur_grille


def main():
    from pyproj import Transformer
    import telecharge
    if not os.path.exists(config.FICHIER):
        sys.exit(config.FICHIER + " introuvable")
    t0 = time.time()
    telecharge.air(config.DEP)
    grilles = [nom for nom in AIR if os.path.exists(f"{AIR_DIR}/{nom}.npy")]
    if not grilles:
        print(f"département {config.DEP} : pas de carte d'air, rien de changé"); return
    e = pd.read_csv(config.FICHIER)
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    ax, ay = map(np.asarray, tr.transform(e.alon.values, e.alat.values))
    bx, by = map(np.asarray, tr.transform(e.blon.values, e.blat.values))
    idx, px, py, _ = echantillonner(ax, ay, bx, by)
    gxy = {}
    for nom in grilles:
        a, m = lire_grille(nom)
        crs = m.get("crs", "EPSG:2154")
        if crs not in gxy:
            gxy[crs] = (px, py) if crs == "EPSG:2154" else tuple(map(np.asarray, Transformer.from_crs(2154, int(crs.split(":")[1]), always_xy=True).transform(px, py)))
        e[nom] = moyenne_par_arete(idx, valeur_grille(a, m, *gxy[crs]), len(e)).astype(np.float32).round(1)
    tmp = config.FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, config.FICHIER)
    v = e.no2_moyan.values
    print(f"département {config.DEP} : air de {config.source_air()[0]} sur {100 * np.isfinite(v).mean():.0f} % des bouts de rue, NO2 moyen {np.nanmean(v):.1f}, "
          f"sur les grands axes {np.nanmean(v[np.isin(e.hw.values, [i for i, h in enumerate(__import__('prepare').HW) if h in ('motorway', 'trunk', 'primary')])]):.1f} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
