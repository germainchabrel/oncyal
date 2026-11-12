"""
Ajoute à out/reseau_06.csv.gz une colonne « acc » : les règles d'accès OpenStreetMap pour la marche et le vélo,
lues comme le font OSRM et GraphHopper (hiérarchie foot > access, bicycle > vehicle > access).

acc (1 octet) :
  bit 0     interdit à pied     (foot=no/private, ou access=private/no/... sans foot=yes, ou barrière privée)
  bit 1     interdit à vélo     (bicycle=no/private, vehicle=..., access=..., ou barrière privée)
  bits 2-3  sens unique vélo + 1 (0 = sens inverse, 1 = double sens, 2 = sens direct)
            tient compte de oneway:bicycle, des contresens cyclables (cycleway=opposite...)
            et des sens uniques implicites (ronds-points)
  bit 4     vélo explicitement autorisé (bicycle=yes/designated/permissive) : chemin utilisable même sans l'option « sentiers »
  bit 5     aménagement cyclable sur la chaussée (bande, piste, couloir bus)

Lancer :  python acces_06.py      (puis python decoupe_06.py)
"""
import glob, os, sys, time
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
PBF = sorted(glob.glob("data/**/*.pbf", recursive=True))[0]
INTERDIT = {"no", "private", "military", "emergency", "restricted", "delivery", "permit", "staff"}
AUTORISE = {"yes", "designated", "permissive", "destination", "official", "public"}
LIEN_HIERARCHIE = {"motorway": 9, "trunk": 8, "primary": 7, "secondary": 6, "tertiary": 5, "unclassified": 4,
                   "residential": 4, "living_street": 3, "service": 2, "pedestrian": 2, "track": 1, "path": 1,
                   "footway": 1, "cycleway": 1, "bridleway": 1, "steps": 1}
AMENAGEMENT = {"lane", "track", "share_busway", "opposite_lane", "opposite_track", "separate"}
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


def bloque(t, mode):
    """True si le mode (foot / bicycle) est interdit d'après les étiquettes t (dict)."""
    chaine = ["foot", "access"] if mode == "foot" else ["bicycle", "vehicle", "access"]
    for k in chaine:
        v = t.get(k)
        if v is None:
            continue
        v = v.split(";")[0].strip()
        if v in AUTORISE:
            return False
        if v in INTERDIT or v == "use_sidepath":
            return True
    return False


def autorise_explicite(t, mode):
    return t.get(mode, "").split(";")[0].strip() in {"yes", "designated", "permissive"}


def sens_velo(t):
    hw = t.get("highway", "")
    ow = t.get("oneway", "")
    if ow in ("yes", "true", "1"):
        s = 1
    elif ow in ("-1", "reverse"):
        s = -1
    elif ow == "no":
        s = 0
    else:   # sens unique implicite
        s = 1 if t.get("junction") in ("roundabout", "circular") or hw in ("motorway", "motorway_link") else 0
    if hw in ("footway", "path", "track", "bridleway", "steps", "pedestrian"):
        s = 0 if ow not in ("yes", "-1") else s
    ob = t.get("oneway:bicycle")
    if ob == "no":
        return 0
    if ob in ("yes", "1"):
        return 1
    if ob == "-1":
        return -1
    if s != 0:
        for k in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both"):
            if t.get(k, "").startswith("opposite"):
                return 0
        for k in ("cycleway:left:oneway", "cycleway:right:oneway", "cycleway:both:oneway"):
            if t.get(k) in ("no", "-1"):
                return 0
    return s


def amenage(t):
    return any(t.get(k, "") in AMENAGEMENT for k in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both"))


def main():
    import osmium
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    t0 = time.time()
    e = pd.read_csv(FICHIER)
    log("réseau lu :", len(e), "bouts de rue")
    ways_utiles = set(np.unique(e.way.values).tolist())

    # 1. barrières (portails, barrières...) fermées au public
    log("1/3 barrières privées (lecture OSM)...")
    bar_pied, bar_velo = set(), set()
    fp = (osmium.FileProcessor(PBF).with_filter(osmium.filter.EntityFilter(osmium.osm.NODE))
          .with_filter(osmium.filter.KeyFilter("barrier")))
    for n in fp:
        t = {k.k: k.v for k in n.tags}
        ferme = t.get("locked") == "yes" or t.get("barrier") in ("wall", "fence", "hedge", "retaining_wall")
        p = bloque(t, "foot") or (ferme and not autorise_explicite(t, "foot"))
        v = bloque(t, "bicycle") or (ferme and not autorise_explicite(t, "bicycle"))
        if p:
            bar_pied.add(n.id)
        if v:
            bar_velo.add(n.id)
    log("   ", len(bar_pied), "barrières fermées aux piétons,", len(bar_velo), "aux vélos")

    # 2. étiquettes des voies
    log("2/3 étiquettes des voies (lecture OSM)...")
    acc_way = {}
    barr = bar_pied | bar_velo
    voies_barriere = {}          # nœud barrière -> [(way, rang hiérarchique, premier/dernier nœud)]
    fp = (osmium.FileProcessor(PBF).with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
          .with_filter(osmium.filter.KeyFilter("highway")))
    for w in fp:
        if w.id not in ways_utiles:
            continue
        t = {k.k: k.v for k in w.tags}
        a = 0
        if bloque(t, "foot"):
            a |= 1
        if bloque(t, "bicycle"):
            a |= 2
        a |= (sens_velo(t) + 1) << 2
        if autorise_explicite(t, "bicycle"):
            a |= 16
        if amenage(t):
            a |= 32
        acc_way[w.id] = a
        refs = [n.ref for n in w.nodes]
        for r in barr.intersection(refs):
            voies_barriere.setdefault(r, []).append((w.id, LIEN_HIERARCHIE.get(t.get("highway", ""), 0)))
    log("   ", len(acc_way), "voies lues")

    # 3. une barrière bloque les voies qui la traversent. À un carrefour, la voie la plus importante
    #    (la route publique d'où part l'allée privée) n'est pas bloquée, sauf si toutes ont le même rang.
    bloq_pied, bloq_velo = set(), set()       # (way, nœud)
    for r, lst in voies_barriere.items():
        top = max(x[1] for x in lst)
        tous_egaux = all(x[1] == top for x in lst)
        for wid, rang in lst:
            if len(lst) > 1 and rang == top and not tous_egaux:
                continue
            if r in bar_pied:
                bloq_pied.add((wid, r))
            if r in bar_velo:
                bloq_velo.add((wid, r))

    log("3/3 fusion...")
    acc = e.way.map(acc_way).fillna(4).astype(np.int64).values    # 4 = rien d'interdit, double sens
    if bloq_pied or bloq_velo:
        def touche(s):
            if not s:
                return np.zeros(len(e), bool)
            ix = pd.MultiIndex.from_tuples(list(s))
            return (pd.MultiIndex.from_arrays([e.way.values, e.a.values]).isin(ix) |
                    pd.MultiIndex.from_arrays([e.way.values, e.b.values]).isin(ix))
        acc = acc | np.where(touche(bloq_pied), 1, 0) | np.where(touche(bloq_velo), 2, 0)
    e["acc"] = acc.astype(np.uint8)

    log("\n   interdits à pied :", int((acc & 1).astype(bool).sum()), "bouts de rue",
        f"({100 * (acc & 1).astype(bool).mean():.1f} %)")
    log("   interdits à vélo :", int((acc & 2).astype(bool).sum()), "bouts de rue",
        f"({100 * ((acc & 2) > 0).mean():.1f} %)")
    sv = ((acc >> 2) & 3) - 1
    log("   sens unique pour les vélos :", int((sv != 0).sum()), "| sens unique auto mais double sens vélo :",
        int(((e.oneway.values != 0) & (sv == 0)).sum()))
    log("   aménagements cyclables sur chaussée :", int(((acc & 32) > 0).sum()))
    tmp = FICHIER + ".tmp"
    e.to_csv(tmp, index=False, compression="gzip")
    os.replace(tmp, FICHIER)
    log(f"\nécrit : {FICHIER} en {time.time() - t0:.0f} s")
    open("out/rapport_acces_06.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
