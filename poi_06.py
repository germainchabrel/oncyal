"""
Points utiles à vélo dans les Alpes-Maritimes, d'après OpenStreetMap :
  0 eau        amenity=drinking_water, ou man_made=water_tap avec drinking_water=yes
  1 arceaux    amenity=bicycle_parking (hors parkings privés)
  2 atelier    amenity=bicycle_repair_station (station de gonflage / réparation en libre-service)
  3 magasin    shop=bicycle
Écrit out/tuiles/poi.json : {"types": [...], "p": [[lat, lon, type, "nom"], ...]} (coordonnées à 5 décimales, ~1 m).
Lancer :  python poi_06.py
"""
import glob, json
import osmium

PBF = sorted(glob.glob("data/**/*.pbf", recursive=True))[0]
BBOX = (6.60, 43.45, 7.75, 44.40)
TYPES = ["eau", "arceaux", "atelier", "magasin"]


def type_de(t):
    if t.get("amenity") == "drinking_water" or (t.get("man_made") == "water_tap" and t.get("drinking_water") == "yes"):
        return 0 if t.get("drinking_water") != "no" else None
    if t.get("amenity") == "bicycle_parking" and t.get("access") not in ("private", "no", "customers"):
        return 1
    if t.get("amenity") == "bicycle_repair_station":
        return 2
    if t.get("shop") == "bicycle":
        return 3
    return None


def main():
    lo0, la0, lo1, la1 = BBOX
    pts, vus = [], set()
    fp = (osmium.FileProcessor(PBF).with_locations()
          .with_filter(osmium.filter.KeyFilter("amenity", "shop", "man_made")))
    for o in fp:
        t = {k.k: k.v for k in o.tags}
        ty = type_de(t)
        if ty is None:
            continue
        try:
            if o.is_node():
                lon, lat = o.location.lon, o.location.lat
            elif o.is_way():
                c = [(n.lon, n.lat) for n in o.nodes]
                lon, lat = sum(x for x, _ in c) / len(c), sum(y for _, y in c) / len(c)
            else:
                continue
        except Exception:
            continue
        if not (lo0 <= lon <= lo1 and la0 <= lat <= la1):
            continue
        cle = (round(lat, 4), round(lon, 4), ty)
        if cle in vus:
            continue
        vus.add(cle)
        nom = (t.get("name") or "")[:40]
        pts.append([round(lat, 5), round(lon, 5), ty] + ([nom] if nom else []))
    json.dump({"types": TYPES, "p": pts}, open("out/tuiles/poi.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for i, n in enumerate(TYPES):
        print(f"{n} : {sum(1 for p in pts if p[2] == i)}")
    print("écrit : out/tuiles/poi.json")


if __name__ == "__main__":
    main()
