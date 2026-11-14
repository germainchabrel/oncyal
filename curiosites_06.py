"""
Découvertes et marchés des Alpes-Maritimes, d'après OpenStreetMap. Écrit out/tuiles/curio.json :
  {"p": [[lat, lon, type, "nom", "détail"], ...],      curiosités à remarquer en passant
   "m": [[lat, lon, rayon_m, "nom", "horaires"], ...]}  marchés dont les horaires sont connus
Types de curiosités :
  0 œuvre d'art      tourism=artwork (fresque, sculpture, installation)
  1 point de vue     tourism=viewpoint
  2 lieu historique  historic=* portant un nom (monument, château, chapelle, ruines, mémorial...)
  3 fontaine         amenity=fountain portant un nom
  4 curiosité        tourism=attraction portant un nom
Le détail donne, quand ils sont connus, l'auteur et la date (artist_name, start_date).
Marchés : amenity=marketplace avec opening_hours ; la page lit les horaires à l'heure du trajet et contourne
un marché en cours (foule, étals : on n'y roule pas).
Lancer :  python curiosites_06.py
"""
import glob, json
import numpy as np
import osmium

PBF = sorted(glob.glob("data/**/*.pbf", recursive=True))[0]
BBOX = (6.60, 43.45, 7.75, 44.40)
ART = {"mural": "fresque", "sculpture": "sculpture", "statue": "statue", "bust": "buste", "installation": "installation",
       "mosaic": "mosaïque", "graffiti": "graffiti", "relief": "bas-relief", "painting": "peinture", "fountain": "fontaine", "stone": "pierre sculptée"}
HIST = {"monument": "monument", "memorial": "mémorial", "castle": "château", "ruins": "ruines", "church": "église", "chapel": "chapelle",
        "fort": "fort", "tower": "tour", "city_gate": "porte de ville", "archaeological_site": "site archéologique", "building": "bâtiment historique",
        "manor": "manoir", "aqueduct": "aqueduc", "bridge": "pont ancien", "citywalls": "remparts", "wayside_shrine": "oratoire",
        "wayside_cross": "croix", "fountain": "fontaine ancienne", "mill": "moulin", "tomb": "tombeau", "monastery": "monastère", "bunker": "blockhaus"}
SANS_INTERET = {"yes", "boundary_stone", "milestone", "memorial_plaque", "district", "road", "cannon", "railway_car"}


def classer(t):
    nom = (t.get("name") or "").strip()
    if t.get("tourism") == "artwork":
        genre = ART.get(t.get("artwork_type"), "œuvre d'art")
        return 0, nom or genre.capitalize(), genre if nom else ""
    if t.get("tourism") == "viewpoint":
        return 1, nom or "Point de vue", ""
    h = t.get("historic")
    if h and nom and h not in SANS_INTERET and t.get("memorial") not in ("plaque", "stolperstein"):
        return 2, nom, HIST.get(h, "")
    if t.get("amenity") == "fountain" and nom:
        return 3, nom, ""
    if t.get("tourism") == "attraction" and nom:
        return 4, nom, ""
    return None


def main():
    lo0, la0, lo1, la1 = BBOX
    pts, marches, vus = [], [], set()
    fp = osmium.FileProcessor(PBF).with_locations().with_filter(osmium.filter.KeyFilter("tourism", "historic", "amenity"))
    for o in fp:
        if o.is_relation():
            continue
        t = {k.k: k.v for k in o.tags}
        marche = t.get("amenity") == "marketplace" and t.get("opening_hours")
        c = None if marche else classer(t)
        if not marche and c is None:
            continue
        try:
            if o.is_node():
                lon, lat, rayon = o.location.lon, o.location.lat, 50
            else:
                xy = np.array([(n.lon, n.lat) for n in o.nodes])
                lon, lat = xy[:, 0].mean(), xy[:, 1].mean()
                rayon = int(np.clip(np.hypot((np.ptp(xy[:, 0])) * 80000, np.ptp(xy[:, 1]) * 111000) / 2, 30, 150))
        except Exception:
            continue
        if not (lo0 <= lon <= lo1 and la0 <= lat <= la1):
            continue
        if marche:
            marches.append([round(lat, 5), round(lon, 5), rayon, (t.get("name") or "Marché")[:50], t["opening_hours"][:200]])
            continue
        if t.get("access") in ("private", "no"):
            continue
        cle = (round(lat, 4), round(lon, 4))
        if cle in vus:
            continue
        vus.add(cle)
        detail = [c[2]] if c[2] else []
        if t.get("artist_name"):
            detail.append(t["artist_name"][:40])
        if t.get("start_date"):
            detail.append(t["start_date"][:12])
        pts.append([round(lat, 5), round(lon, 5), c[0], c[1][:60], ", ".join(detail)])
    json.dump({"p": pts, "m": marches}, open("out/tuiles/curio.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for i, n in enumerate(["œuvres d'art", "points de vue", "lieux historiques", "fontaines", "curiosités"]):
        print(f"{n} : {sum(1 for p in pts if p[2] == i)}")
    print("marchés avec horaires :", len(marches))
    print("écrit : out/tuiles/curio.json")


if __name__ == "__main__":
    main()
