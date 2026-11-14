"""
Bruit mesuré : corrige le bruit des rues avec les mesures faites par des habitants avec l'application NoiseCapture
(projet Noise-Planet, CNRS et Université Gustave Eiffel ; données sous licence ODbL).
Source : service WFS de Noise-Planet, couche noisecapture:noisecapture_area (hexagones d'environ 15 m, niveau moyen
LAeq et nombre de mesures), enregistrée dans data/noisecapture/areas_06.geojson. Pour la rafraîchir :
  https://onomap-gs.noise-planet.org/geoserver/noisecapture/ows?service=WFS&version=1.0.0&request=GetFeature
  &typeName=noisecapture:noisecapture_area&outputFormat=application/json&srsName=EPSG:4326&bbox=6.6,43.45,7.75,44.4,EPSG:4326
Règle : un bout de rue dont le milieu est à moins de 15 m du centre d'un hexagone ayant au moins 10 mesures reçoit
la moyenne entre le bruit du modèle et le bruit mesuré, sans s'écarter de plus de 6 dB du modèle (une mesure au
téléphone est un instantané, le modèle une moyenne annuelle : on corrige, on ne remplace pas).
Colonnes : noise et noise_n corrigés ; noise_modele et noise_n_modele gardent les valeurs d'avant (pour relancer le
script sans corriger deux fois) ; mesure = 1 pour les bouts de rue corrigés.
Lancer :  python mesures_06.py      (après avions_06.py, avant decoupe_06.py)
"""
import json, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
SOURCE = "data/noisecapture/areas_06.geojson"
MIN_MESURES, RAYON, ECART_MAX = 10, 15.0, 6.0


def main():
    from scipy.spatial import cKDTree
    from pyproj import Transformer
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    e = pd.read_csv(FICHIER)
    if not os.path.exists(SOURCE):
        print(SOURCE, "absent : aucune correction par les mesures"); return
    t0 = time.time()
    hexa = []
    for f in json.load(open(SOURCE, encoding="utf-8"))["features"]:
        p, g = f["properties"], f["geometry"]
        if g["type"] != "Polygon" or (p.get("measure_count") or 0) < MIN_MESURES or not p.get("laeq"):
            continue
        c = np.array(g["coordinates"][0])[:-1]
        hexa.append((c[:, 0].mean(), c[:, 1].mean(), float(p["laeq"])))
    hexa = np.array(hexa)
    print(len(hexa), f"hexagones avec au moins {MIN_MESURES} mesures")
    if "noise_modele" not in e:
        e["noise_modele"], e["noise_n_modele"] = e["noise"], e["noise_n"]
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    hx, hy = tr.transform(hexa[:, 0], hexa[:, 1])
    mx, my = tr.transform(((e.alon + e.blon) / 2).values, ((e.alat + e.blat) / 2).values)
    d, i = cKDTree(np.c_[hx, hy]).query(np.c_[mx, my], distance_upper_bound=RAYON)
    ok = np.isfinite(d)
    mod, modn = e.noise_modele.values.astype(float), e.noise_n_modele.values.astype(float)
    mes = np.where(ok, hexa[np.minimum(i, len(hexa) - 1), 2], np.nan)
    base = np.where(np.isfinite(mod), mod, 45.0)
    corr = np.clip((mes - base) / 2, -ECART_MAX, ECART_MAX)
    e["noise"] = np.where(ok, np.round(base + corr, 1), mod)
    e["noise_n"] = np.where(ok & np.isfinite(modn), np.round(modn + corr, 1), modn)
    e["mesure"] = ok.astype(np.int8)
    L = e.len_m.values
    print(f"bouts de rue corrigés : {int(ok.sum())} ({L[ok].sum() / 1000:.1f} km) ; correction moyenne {np.nanmean(corr[ok]):+.1f} dB, "
          f"de {np.nanmin(corr[ok]):+.1f} à {np.nanmax(corr[ok]):+.1f} dB")
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    print(f"écrit : {FICHIER} en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
