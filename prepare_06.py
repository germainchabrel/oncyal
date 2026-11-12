"""
Préparation des données — Alpes-Maritimes (06)
Lit : routes OSM (PACA) + bruit Cerema (routier + ferroviaire, type A, Lden) + air AtmoSud 2024 (25 m)
Écrit : out/reseau_06.csv.gz  (une ligne par bout de rue, avec bruit et air)
        out/rapport_06.txt    (contrôles : à me coller)
Lancer :  python prepare_06.py
"""
import glob, math, os, sys, time
import numpy as np
import pandas as pd

BBOX = (6.60, 43.45, 7.75, 44.40)           # lon min, lat min, lon max, lat max (06)
_pbf = sorted(glob.glob("data/**/*.pbf", recursive=True))
if not _pbf:
    sys.exit("Aucun fichier .pbf trouvé dans data\\osm (ni ailleurs dans data). Vérifie le téléchargement.")
PBF = _pbf[0]
print("fichier routes utilisé :", PBF)
AIR_DIR = "data/atmosud"
AIR = ["no2_moyan", "pm10_moyan", "pm25_moyan", "icair365"]
PAS_ECHANT = 25.0                           # un point d'échantillon tous les 25 m le long de chaque bout de rue
OUT = "out"
os.makedirs(OUT, exist_ok=True)
T0 = time.time()
rapport = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    rapport.append(s)


# Types de voies gardés, et bruit estimé au bord de la voie (dB) quand AUCUNE carte officielle ne la couvre.
# (4e colonne du code : ordre de grandeur, repris du modèle de ton site)
L0 = {"motorway": 78, "trunk": 74, "primary": 70, "secondary": 66, "tertiary": 62, "unclassified": 56,
      "residential": 54, "living_street": 50, "service": 48, "pedestrian": 45, "track": 40, "path": 40,
      "footway": 40, "cycleway": 40, "bridleway": 40, "steps": 40}
for k in ("motorway", "trunk", "primary", "secondary", "tertiary"):
    L0[k + "_link"] = L0[k]
HW = sorted(L0)
HWI = {h: i for i, h in enumerate(HW)}


# ---------------------------------------------------------------- 1. ROUTES OSM
def lire_osm():
    import osmium
    log("1/5 lecture des routes OSM (quelques minutes)...")
    fp = (osmium.FileProcessor(PBF).with_locations()
          .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
          .with_filter(osmium.filter.KeyFilter("highway")))
    lo0, la0, lo1, la1 = BBOX
    ways = []
    for o in fp:
        hw = o.tags.get("highway")
        if hw not in L0:
            continue
        try:
            pts = [(n.ref, n.lon, n.lat) for n in o.nodes]
        except Exception:
            continue
        if len(pts) < 2 or not any(lo0 <= p[1] <= lo1 and la0 <= p[2] <= la1 for p in pts):
            continue
        t = o.tags
        ow = t.get("oneway", "")
        ow = 1 if ow in ("yes", "true", "1") else -1 if ow == "-1" else 0
        lit = t.get("lit", "")
        lit = 1 if lit in ("yes", "24/7", "automatic", "sunset-sunrise") else 0 if lit == "no" else -1
        ways.append((o.id, HWI[hw], ow, lit, pts))
    if not ways:
        raise SystemExit("aucune route lue : le fichier OSM est-il bien dans data/osm ?")
    log("   ", len(ways), "routes lues")
    return ways


def construire_aretes(ways):
    wid, hw, ow, lit, na, nb, alon, alat, blon, blat = ([] for _ in range(10))
    for i, h, o, l, pts in ways:
        for (r1, x1, y1), (r2, x2, y2) in zip(pts[:-1], pts[1:]):
            if r1 == r2:
                continue
            wid.append(i); hw.append(h); ow.append(o); lit.append(l)
            na.append(r1); nb.append(r2); alon.append(x1); alat.append(y1); blon.append(x2); blat.append(y2)
    return pd.DataFrame(dict(way=np.array(wid, dtype=np.int64), hw=np.array(hw, dtype=np.int8),
                             oneway=np.array(ow, dtype=np.int8), lit=np.array(lit, dtype=np.int8),
                             a=np.array(na, dtype=np.int64), b=np.array(nb, dtype=np.int64),
                             alon=np.array(alon), alat=np.array(alat), blon=np.array(blon), blat=np.array(blat)))


# ---------------------------------------------------------------- 2. POINTS D'ÉCHANTILLON
def echantillonner(ax, ay, bx, by):
    """Pour chaque bout de rue, des points tous les ~25 m. Retourne (indice du bout de rue, x, y) + longueurs."""
    L = np.hypot(bx - ax, by - ay)
    n = np.clip(np.ceil(L / PAS_ECHANT), 1, 400).astype(np.int64)
    idx = np.repeat(np.arange(len(L)), n)
    debut = np.cumsum(n) - n
    k = np.arange(n.sum()) - np.repeat(debut, n)
    t = (k + 0.5) / n[idx]
    return idx, ax[idx] + t * (bx - ax)[idx], ay[idx] + t * (by - ay)[idx], L


def moyenne_par_arete(idx, vals, n_aretes):
    ok = np.isfinite(vals)
    s = np.bincount(idx[ok], weights=vals[ok], minlength=n_aretes)
    c = np.bincount(idx[ok], minlength=n_aretes)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c > 0, s / c, np.nan)


# ---------------------------------------------------------------- 3. AIR (grille AtmoSud)
def lire_grille(nom):
    a = np.load(f"{AIR_DIR}/{nom}.npy")
    import json
    return a, json.load(open(f"{AIR_DIR}/{nom}.json"))


def valeur_grille(a, meta, x, y, dx=0.0, dy=0.0):
    col = np.floor((x + dx - meta["x0"]) / meta["pas"]).astype(np.int64)
    lig = np.floor((meta["y1"] - (y + dy)) / meta["pas"]).astype(np.int64)
    ok = (col >= 0) & (col < meta["colonnes"]) & (lig >= 0) & (lig < meta["lignes"])
    v = np.full(x.shape, np.nan, dtype=np.float32)
    v[ok] = a[lig[ok], col[ok]]
    return v


# ---------------------------------------------------------------- 4. BRUIT (polygones Cerema)
def bruit_cerema(px, py):
    import geopandas as gpd
    polys = []
    for motif in ("*R_A_LD_S_006.shp", "*F_A_LD_S_006.shp"):
        for f in glob.glob("data/cerema/**/" + motif, recursive=True):
            g = gpd.read_file(f)
            g = g.set_crs(2154, allow_override=True)
            g["lvl"] = g["LEGENDE"].astype(float)
            polys.append(g[["lvl", "geometry"]])
            log("   ", os.path.basename(f), ":", len(g), "zones")
    if not polys:
        raise SystemExit("fichiers Cerema introuvables dans data/cerema")
    polys = gpd.GeoDataFrame(pd.concat(polys, ignore_index=True), crs=2154)
    res = np.full(len(px), np.nan)
    pas = 400_000
    for d in range(0, len(px), pas):
        pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(px[d:d + pas], py[d:d + pas]), crs=2154)
        j = gpd.sjoin(pts, polys, how="inner", predicate="within")
        if len(j):
            s = j.groupby(level=0)["lvl"].max()
            res[d + s.index.values] = s.values + 2.5     # milieu de la tranche : 55 -> 57,5 dB
        log(f"    bruit : {min(d + pas, len(px))}/{len(px)} points")
    return res


# ---------------------------------------------------------------- PRINCIPAL
def main():
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, 2154, always_xy=True)

    e = construire_aretes(lire_osm())
    n = len(e)
    log("2/5", n, "bouts de rue")
    ax, ay = tr.transform(e.alon.values, e.alat.values)
    bx, by = tr.transform(e.blon.values, e.blat.values)
    ax, ay, bx, by = map(np.asarray, (ax, ay, bx, by))
    idx, px, py, L = echantillonner(ax, ay, bx, by)
    e["len_m"] = L.round(1)
    log("   ", len(px), "points d'échantillon,", round(L.sum() / 1000), "km de voies")

    log("3/5 air (AtmoSud)...")
    grilles = {nom: lire_grille(nom) for nom in AIR}
    for nom, (a, m) in grilles.items():
        e[nom] = moyenne_par_arete(idx, valeur_grille(a, m, px, py), n).astype(np.float32).round(1)

    log("4/5 bruit (Cerema)...")
    bc = bruit_cerema(px, py)
    e["noise_cerema"] = moyenne_par_arete(idx, bc, n)
    couvert = np.isfinite(e["noise_cerema"].values)
    est = np.array([L0[HW[h]] for h in e.hw.values], dtype=float)
    e["noise"] = np.where(couvert, e["noise_cerema"].values, est).round(1)
    e["noise_src"] = couvert.astype(np.int8)     # 1 = carte officielle, 0 = estimation d'après le type de voie
    e = e.drop(columns=["noise_cerema"])

    log("5/5 contrôles")
    e["hwn"] = [HW[h] for h in e.hw.values]
    log("   part des bouts de rue avec air valide :", f"{100 * e.no2_moyan.notna().mean():.0f} %")
    log("   part avec bruit officiel :", f"{100 * e.noise_src.mean():.0f} %")
    log("\n   moyennes par type de voie (NO2 µg/m3, bruit dB, nombre) :")
    g = e.groupby("hwn").agg(no2=("no2_moyan", "mean"), bruit=("noise", "mean"), n=("a", "size")).round(1)
    log(g.sort_values("no2", ascending=False).to_string())

    # Contrôle de calage de la grille d'air : sur les grands axes, la moyenne de NO2 doit être maximale à décalage 0.
    # Si le maximum est ailleurs, la grille est décalée.
    ax_ = e.hwn.isin(["motorway", "trunk", "primary"]).values[idx]
    a, m = grilles["no2_moyan"]
    log("\n   calage de la grille d'air (NO2 moyen sur les grands axes, décalage en mètres) :")
    log("          dy=-50   -25     0     +25    +50")
    best = (None, -1)
    for dx in (-50, -25, 0, 25, 50):
        ligne = []
        for dy in (-50, -25, 0, 25, 50):
            v = np.nanmean(valeur_grille(a, m, px[ax_], py[ax_], dx, dy))
            ligne.append(v)
            if v > best[1]:
                best = ((dx, dy), v)
        log(f"   dx={dx:+4d} " + " ".join(f"{v:6.2f}" for v in ligne))
    log("   maximum atteint pour (dx, dy) =", best[0], "->", "calage OK" if best[0] == (0, 0) else "CALAGE A CORRIGER")

    e.drop(columns=["hwn"]).to_csv(f"{OUT}/reseau_06.csv.gz", index=False, compression="gzip")
    log(f"\nécrit : {OUT}/reseau_06.csv.gz ({os.path.getsize(OUT + '/reseau_06.csv.gz') // 1_000_000} Mo) en {time.time() - T0:.0f} s")
    open(f"{OUT}/rapport_06.txt", "w", encoding="utf-8").write("\n".join(rapport))


if __name__ == "__main__":
    main()
