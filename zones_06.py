"""
Accès incertains : ajoute à out/reseau_06.csv.gz une colonne « zone » (0 = aucune) et écrit out/tuiles/zones.json.

Les lieux fermés (hippodromes, stades, campus, hôpitaux, cimetières, parcs fermés la nuit) sont les plus calmes :
un calcul qui cherche le calme est attiré par eux, alors qu'OpenStreetMap ne dit souvent ni qu'ils ferment, ni quand.
Trois sortes de zones, de la plus sûre à la plus incertaine :
  horaire   horaires connus : opening_hours sur le lieu ou la voie, ou accès conditionnel du type
            « access:conditional = no @ (20:00-08:00) ». La page ferme la voie aux heures de fermeture.
  interdit  voie sans indication d'accès à l'intérieur d'un site fermé au public, gardé ou clôturé :
            hippodrome (guérite, contrôle des entrées), terrain militaire, prison, aérodrome. Traitée comme privée.
  enceinte  voie sans indication d'accès À L'INTÉRIEUR d'un site souvent clos, sans horaires :
            site sportif, golf, hôpital, établissement scolaire, cimetière, camping, zoo...
            La page ne l'emprunte que s'il n'existe aucun autre chemin, et prévient si le trajet y passe.
  parc      voie sans indication d'accès dans un parc ou un jardin sans horaires : souvent fermé la nuit.
            Pénalisée et signalée seulement de nuit.
Une voie avec une indication d'accès explicite (access, foot, bicycle...) garde la sienne : elle n'est pas « incertaine ».
Les grands axes (primary, secondary, tertiary) et les pistes cyclables ne sont jamais classés.

zones.json : [{"t": "horaire"|"interdit"|"enceinte"|"parc", "n": nom, "k": genre de lieu, "oh": horaires, "inv": true si les
horaires décrivent la FERMETURE (accès conditionnel)}] ; l'index 0 est vide.
Lancer :  python zones_06.py      (après acces_06.py, avant decoupe_06.py)
"""
import glob, json, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
PBF = sorted(glob.glob("data/**/*.pbf", recursive=True))[0]
BBOX = (6.60, 43.45, 7.75, 44.40)
INTERDIT = {"no", "private", "military", "emergency", "restricted", "delivery", "permit", "staff"}
EXPLICITE = ("access", "foot", "bicycle", "vehicle")
JAMAIS = {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link", "motorway", "motorway_link",
          "trunk", "trunk_link", "cycleway"}
FERMES = {"hippodrome", "terrain militaire", "prison", "aérodrome"}   # sites fermés au public : voies sans accès explicite = privées
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def genre(t):
    """Genre de site souvent clos, ou None."""
    if t.get("sport") == "horse_racing":
        return "hippodrome"
    l, a, lu, to = t.get("leisure"), t.get("amenity"), t.get("landuse"), t.get("tourism")
    if l in ("sports_centre", "stadium"): return "site sportif"
    if l == "golf_course": return "golf"
    if l in ("horse_riding", "water_park"): return "centre de loisirs"
    if a in ("hospital",): return "hôpital"
    if a in ("school", "college", "university", "kindergarten"): return "établissement scolaire"
    if a == "prison": return "prison"
    if a == "grave_yard" or lu == "cemetery": return "cimetière"
    if a == "monastery" or lu == "religious": return "site religieux"
    if lu == "military": return "terrain militaire"
    if to in ("zoo", "theme_park"): return "parc de loisirs"
    if to in ("camp_site", "caravan_site"): return "camping"
    if t.get("aeroway") == "aerodrome": return "aérodrome"
    return None


def est_parc(t):
    return t.get("leisure") in ("park", "garden") and t.get("access") not in ("private", "no")


def conditionnel(t):
    """Horaires de fermeture d'une voie d'après les accès conditionnels (vélo d'abord), ou None."""
    for k in ("bicycle:conditional", "vehicle:conditional", "access:conditional", "foot:conditional"):
        v = t.get(k)
        if not v:
            continue
        for part in v.split(";"):
            if "@" not in part:
                continue
            val, cond = part.split("@", 1)
            cond = cond.strip()
            if cond.startswith("(") and cond.endswith(")"):
                cond = cond[1:-1]
            if val.strip() in INTERDIT and cond:
                return cond.strip()
    return None


def main():
    import osmium
    import geopandas as gpd
    from shapely import wkb
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    t0 = time.time()
    zones = [{}]                         # index 0 : aucune zone
    cle_zone = {}

    def zone(d):
        c = json.dumps(d, sort_keys=True, ensure_ascii=False)
        if c not in cle_zone:
            cle_zone[c] = len(zones); zones.append(d)
        return cle_zone[c]

    log("1/3 lecture OSM : sites, parcs, horaires...")
    fab = osmium.geom.WKBFactory()
    lo0, la0, lo1, la1 = BBOX
    geoms, zid, prio = [], [], []
    voie_zone = {}                       # voie OSM -> zone (horaires propres à la voie)
    voie_explicite = set()               # voies avec une indication d'accès explicite
    fp = (osmium.FileProcessor(PBF).with_locations()
          .with_areas(osmium.filter.KeyFilter("leisure", "amenity", "landuse", "tourism", "aeroway", "sport"))
          .with_filter(osmium.filter.KeyFilter("leisure", "amenity", "landuse", "tourism", "aeroway", "sport", "highway")))
    for o in fp:
        t = {k.k: k.v for k in o.tags}
        if o.is_area():
            g_ = genre(t); parc = est_parc(t); oh = t.get("opening_hours")
            if not (g_ or parc):
                continue
            try:
                g = wkb.loads(fab.create_multipolygon(o), hex=True)
            except Exception:
                continue
            b = g.bounds
            if b[2] < lo0 or b[0] > lo1 or b[3] < la0 or b[1] > la1:
                continue
            nom = t.get("name", "")[:60]
            if oh and oh.strip() not in ("24/7",):
                z, p = zone({"t": "horaire", "n": nom, "k": g_ or "parc", "oh": oh.strip()}), 3
            elif oh:
                continue                 # ouvert en permanence : rien à signaler
            elif g_ in FERMES:
                z, p = zone({"t": "interdit", "n": nom, "k": g_}), 4
            elif g_:
                z, p = zone({"t": "enceinte", "n": nom, "k": g_}), 2
            else:
                z, p = zone({"t": "parc", "n": nom, "k": "parc"}), 1
            geoms.append(g); zid.append(z); prio.append(p)
        elif o.is_way() and "highway" in t:
            if any(k in t for k in EXPLICITE):
                voie_explicite.add(o.id)
            cond = conditionnel(t)
            if cond:
                voie_zone[o.id] = zone({"t": "horaire", "n": t.get("name", "")[:60], "k": "voie", "oh": cond, "inv": True})
            elif t.get("opening_hours") and t.get("opening_hours").strip() != "24/7":
                voie_zone[o.id] = zone({"t": "horaire", "n": t.get("name", "")[:60], "k": "voie", "oh": t["opening_hours"].strip()})
    log("   ", len(geoms), "sites ou parcs,", len(voie_zone), "voies à horaires propres,", len(zones) - 1, "zones distinctes")

    log("2/3 position des bouts de rue...")
    e = pd.read_csv(FICHIER)
    mx, my = ((e.alon + e.blon) / 2).values, ((e.alat + e.blat) / 2).values
    poly = gpd.GeoDataFrame({"z": zid, "p": prio, "aire": [g.area for g in geoms]}, geometry=geoms, crs=4326)
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(mx, my), crs=4326)
    j = gpd.sjoin(pts, poly, how="inner", predicate="within")
    # plusieurs zones possibles : la plus contraignante (interdit > horaire > enceinte > parc), puis la plus petite
    j = j.sort_values(["p", "aire"], ascending=[False, True])
    j = j[~j.index.duplicated(keep="first")]
    z = np.zeros(len(e), np.int32)
    z[j.index.values] = j.z.values

    log("3/3 règles...")
    noms_hw = json.load(open("out/tuiles/hw.json")) if os.path.exists("out/tuiles/hw.json") else []
    jamais = np.array([noms_hw[h] in JAMAIS if h < len(noms_hw) else False for h in e.hw.values])
    expl = e.way.isin(voie_explicite).values
    types = np.array([zones[i].get("t", "") for i in range(len(zones))])
    t_e = types[z]
    # une voie à accès explicite ou un grand axe n'est jamais « incertain » (mais garde des horaires de site connus)
    z[(t_e != "horaire") & (expl | jamais)] = 0
    z[(t_e == "horaire") & jamais] = 0
    # horaires propres à la voie : prioritaires
    vz = e.way.map(voie_zone)
    ok = vz.notna().values
    z[ok] = vz[ok].astype(int).values
    if z.max() > 65535:
        sys.exit("trop de zones distinctes pour 2 octets")
    e["zone"] = z

    L = e.len_m.values
    for t in ("interdit", "horaire", "enceinte", "parc"):
        m = types[z] == t
        log(f"   {t} : {int(m.sum())} bouts de rue, {L[m].sum() / 1000:.0f} km")
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    json.dump(zones, open("out/tuiles/zones.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"\nécrit : {FICHIER} et out/tuiles/zones.json ({len(zones) - 1} zones) en {time.time() - t0:.0f} s")
    open("out/rapport_zones_06.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
