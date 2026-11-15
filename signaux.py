"""
Feux tricolores : écrit out/signaux.npy, la liste des nœuds OpenStreetMap équipés de feux
(highway=traffic_signals, ou passage piéton crossing=traffic_signals), dans les Alpes-Maritimes.
assemble.py en tire un octet par nœud dans les tuiles ; la page pénalise chaque feu rencontré (arrêt, attente
au milieu des gaz d'échappement) et chaque traversée d'un grand axe.
Lancer :  python signaux.py
"""
import glob
import numpy as np
import osmium

import config


def main():
    lo0, la0, lo1, la1 = config.bbox()
    ids = []
    fp = (osmium.FileProcessor(config.pbf()).with_filter(osmium.filter.EntityFilter(osmium.osm.NODE))
          .with_filter(osmium.filter.KeyFilter("highway", "crossing")))
    for n in fp:
        t = {k.k: k.v for k in n.tags}
        if t.get("highway") == "traffic_signals" or t.get("crossing") == "traffic_signals":
            try:
                if lo0 <= n.location.lon <= lo1 and la0 <= n.location.lat <= la1:
                    ids.append(n.id)
            except Exception:
                pass
    np.save(f"{config.DOSSIER}/signaux.npy", np.array(sorted(set(ids)), dtype=np.int64))
    print(len(set(ids)), f"nœuds à feux écrits dans {config.DOSSIER}/signaux.npy")


if __name__ == "__main__":
    main()
