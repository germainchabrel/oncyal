"""
Assemble les fichiers du site (out/tuiles) à partir de tous les départements traités (out/dep/<code>/).

Chaque bout de rue appartient à un seul département : celui qui contient son milieu (sinon le plus proche à moins
de 5 km). Une tuile à cheval sur deux départements reçoit donc les rues des deux, sans doublon. Les départements
sont lus l'un après l'autre ; seules les tuiles de frontière attendent en mémoire.

Taille des tuiles : la case de base fait 0,05° x 0,04° (environ 4 x 4,5 km). Là où il y a peu de rues, les cases
sont regroupées par blocs de 2 x 2, 4 x 4 ou 8 x 8 tant que le bloc reste sous SEUIL bouts de rue : moins de
fichiers (Cloudflare en accepte 20 000 par site sur l'offre gratuite) et moins de téléchargements à la campagne.
Un fichier s'appelle <niveau>_<X>_<Y>.bin : niveau 0 = une case, 1 = 2 x 2 cases, 2 = 4 x 4, 3 = 8 x 8 ; X et Y sont
les numéros de case divisés par 2 puissance niveau.

Format « CC02 » d'une tuile, écrite en gzip (Cloudflare ne compresse pas les fichiers binaires) :
  en-tête  'CC02', n (u32), m (u32), j (u32)
  nœuds    id (f64), lon (i32, en 1e-6 degré), lat (i32), feux (u8)                         chacun x n
  rues     a (u32), b (u32), longueur (u16, en dm), type de voie (u8), accès (u8, voir acces.py),
           bruit (u8 : (dB - 30) x 4), bruit de nuit (u8, idem), NO2 (u8 : µg/m3 x 2), indice d'air (u8 : x 10),
           zone d'accès incertain (u16 : rang dans la liste « z » ci-dessous, 0 = aucune), accidents de vélo (u8)   chacun x m
  JSON     {"z": [zones d'accès incertain, la première vide], "p": [[lat, lon, type, nom], ...points utiles]}   sur j octets
255 = pas de donnée pour les valeurs sur 1 octet.

Écrit aussi index.json ({"ts_lon", "ts_lat", "t": [niveau, X, Y, niveau, X, Y, ...], "deps": [[code, nom], ...]}) et hw.json.
Lancer :  python assemble.py            (tous les départements présents dans out/dep)
"""
import glob, gzip, json, os, struct, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import config

SORTIE = "out/tuiles"
TS_LON, TS_LAT = 0.05, 0.04
MAGIC = b"CC02"
SEUIL = 30000                       # un bloc de cases est écrit en un seul fichier s'il compte au plus ce nombre de bouts de rue
NIVEAU_MAX = 3
NA = 255
COLS = ["a", "b", "alon", "alat", "blon", "blat", "len_m", "hw", "acc", "noise", "noise_n", "no2_moyan", "icair365", "zone", "acc_velo"]


def q(v, echelle, decalage=0.0):
    """Valeur -> octet 0..254 ; 255 = pas de donnée."""
    v = np.asarray(v, dtype=float)
    o = np.clip(np.round((v - decalage) * echelle), 0, 254)
    o[~np.isfinite(v)] = NA
    return o.astype(np.uint8)


def cle(lon, lat):
    return np.floor(lon / TS_LON).astype(np.int64) * 100000 + np.floor(lat / TS_LAT).astype(np.int64)


def preparer(dep):
    """Rues et points utiles du département, réduits à ceux qui lui appartiennent, rangés par zone.
    Gardé dans out/dep/<code>/part.npz tant que reseau.csv.gz n'a pas changé."""
    d = f"out/dep/{dep}"
    src, cache = f"{d}/reseau.csv.gz", f"{d}/part.npz"
    if os.path.exists(cache) and os.path.getmtime(cache) > max(os.path.getmtime(f) for f in glob.glob(d + "/*") if not f.endswith("part.npz")):
        return dict(np.load(cache, allow_pickle=False))
    e = pd.read_csv(src, usecols=lambda c: c in COLS)
    m = len(e)
    mx, my = ((e.alon + e.blon) / 2).values, ((e.alat + e.blat) / 2).values
    garde = config.departement_des_points(mx, my) == dep
    e, mx, my = e[garde].reset_index(drop=True), mx[garde], my[garde]
    k = cle(mx, my)
    o = np.argsort(k, kind="stable")
    e, k = e.iloc[o].reset_index(drop=True), k[o]
    col = lambda nom, defaut: e[nom].values if nom in e else np.full(len(e), defaut)
    p = json.load(open(f"{d}/poi.json", encoding="utf-8"))["p"] if os.path.exists(f"{d}/poi.json") else []
    plat, plon = np.array([x[0] for x in p], float), np.array([x[1] for x in p], float)
    pg = config.departement_des_points(plon, plat) == dep if len(p) else np.zeros(0, bool)
    part = dict(
        k=k, a=e.a.values.astype(np.int64), b=e.b.values.astype(np.int64),
        alon=np.round(e.alon.values * 1e6).astype(np.int32), alat=np.round(e.alat.values * 1e6).astype(np.int32),
        blon=np.round(e.blon.values * 1e6).astype(np.int32), blat=np.round(e.blat.values * 1e6).astype(np.int32),
        len=np.clip(np.round(e.len_m.values * 10), 0, 65535).astype(np.uint16), hw=e.hw.values.astype(np.uint8),
        acc=col("acc", 4).astype(np.uint8), noise=q(e.noise.values, 4, 30), noise_n=q(col("noise_n", np.nan), 4, 30),
        no2=q(col("no2_moyan", np.nan), 2), ica=q(col("icair365", np.nan), 10),
        zone=np.nan_to_num(col("zone", 0)).astype(np.int32), accv=np.minimum(np.nan_to_num(col("acc_velo", 0)), 254).astype(np.uint8),
        sig=np.load(f"{d}/signaux.npy") if os.path.exists(f"{d}/signaux.npy") else np.zeros(0, np.int64),
        plat=plat[pg], plon=plon[pg], ptype=np.array([x[2] for x in p], np.uint8)[pg] if len(p) else np.zeros(0, np.uint8),
        pnom=np.array([(x[3] if len(x) > 3 else "") for x in p], dtype="U40")[pg] if len(p) else np.zeros(0, "U40"),
        total=np.array([m]),
    )
    part["pk"] = cle(part["plon"], part["plat"])
    np.savez(cache, **part)
    return part


def decoupage(cles, nombres):
    """Pour chaque case de base (clé), le fichier qui la contient : (niveau, X, Y). Du plus gros bloc au plus petit."""
    x, y = cles // 100000, cles % 100000
    niveau = np.zeros(len(cles), np.int64)
    libre = np.ones(len(cles), bool)
    for L in range(NIVEAU_MAX, 0, -1):
        bloc = (x >> L) * 100000 + (y >> L)
        u, inv = np.unique(bloc, return_inverse=True)
        total = np.bincount(inv, weights=nombres, minlength=len(u))
        ok = libre & (total[inv] <= SEUIL)
        niveau[ok] = L; libre &= ~ok
    return {int(k): (int(L), int(a >> L), int(b >> L)) for k, L, a, b in zip(cles, niveau, x, y)}


def morceau(part, zones, ks):
    """Les rues et points utiles d'un département dans un fichier (une ou plusieurs cases de base)."""
    bornes = [np.searchsorted(part["k"], [k, k + 1]) for k in ks]
    ix = np.concatenate([np.arange(i0, i1) for i0, i1 in bornes]) if bornes else np.zeros(0, np.int64)
    s = {c: part[c][ix] for c in ("a", "b", "alon", "alat", "blon", "blat", "len", "hw", "acc", "noise", "noise_n", "no2", "ica", "zone", "accv")}
    pm = np.isin(part["pk"], ks)
    return dict(s=s, sig=part["sig"], zones=zones, poi=[[round(float(la), 5), round(float(lo), 5), int(t)] + ([str(n)] if n else [])
                                                         for la, lo, t, n in zip(part["plat"][pm], part["plon"][pm], part["ptype"][pm], part["pnom"][pm])])


def ecrire(chemin, morceaux):
    cat = lambda c: np.concatenate([x["s"][c] for x in morceaux])
    a, b = cat("a"), cat("b")
    m = len(a)
    noeuds, premier, inv = np.unique(np.concatenate([a, b]), return_index=True, return_inverse=True)
    lon, lat = np.concatenate([cat("alon"), cat("blon")])[premier], np.concatenate([cat("alat"), cat("blat")])[premier]
    feux = np.zeros(len(noeuds), bool)
    for x in morceaux:
        feux |= np.isin(noeuds, x["sig"])
    # zones d'accès incertain : numéros propres à la tuile
    table, zl = [{}], []
    for x in morceaux:
        z = x["s"]["zone"]
        u, r = np.unique(z, return_inverse=True)
        rang = np.zeros(len(u), np.int64)
        for i, v in enumerate(u):
            if v > 0 and v < len(x["zones"]):
                rang[i] = len(table); table.append(x["zones"][v])
        zl.append(rang[r])
    zone = np.concatenate(zl) if zl else np.zeros(0, np.int64)
    if len(table) > 65535:
        sys.exit("trop de zones dans une tuile")
    js = json.dumps({"z": table, "p": [p for x in morceaux for p in x["poi"]]}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blocs = [np.asarray(noeuds, "<f8"), lon.astype("<i4"), lat.astype("<i4"), feux.astype(np.uint8),
             inv[:m].astype("<u4"), inv[m:].astype("<u4"), cat("len").astype("<u2"), cat("hw"), cat("acc"),
             cat("noise"), cat("noise_n"), cat("no2"), cat("ica"), zone.astype("<u2"), cat("accv")]
    corps = MAGIC + struct.pack("<III", len(noeuds), m, len(js)) + b"".join(x.tobytes() for x in blocs) + js
    Path(chemin).write_bytes(gzip.compress(corps, compresslevel=9, mtime=0))
    return m


def lire_tuile(chemin):
    """Relit une tuile (contrôle)."""
    d = gzip.decompress(Path(chemin).read_bytes())
    assert d[:4] == MAGIC
    n, m, j = struct.unpack("<III", d[4:16])
    p = 16
    def lire(dt, k):
        nonlocal p
        x = np.frombuffer(d, dtype=dt, count=k, offset=p); p += x.nbytes; return x
    t = {"id": lire("<f8", n), "lon": lire("<i4", n) / 1e6, "lat": lire("<i4", n) / 1e6, "feux": lire("u1", n),
         "a": lire("<u4", m), "b": lire("<u4", m), "len_m": lire("<u2", m) / 10.0, "hw": lire("u1", m), "acc": lire("u1", m)}
    for nom, ech, dec in (("noise", 4, 30), ("noise_n", 4, 30), ("no2", 2, 0), ("ica", 10, 0)):
        o = lire("u1", m).astype(float); t[nom] = np.where(o == NA, np.nan, o / ech + dec)
    t["zone"] = lire("<u2", m); t["accv"] = lire("u1", m)
    t["json"] = json.loads(d[p:p + j].decode("utf-8"))
    assert p + j == len(d)
    return t


def main():
    from prepare import HW
    t0 = time.time()
    deps = sorted(os.path.basename(os.path.dirname(f)) for f in glob.glob("out/dep/*/reseau.csv.gz"))
    if len(sys.argv) > 1:
        deps = [d for d in deps if d in sys.argv[1:]]
    if not deps:
        sys.exit("aucun département dans out/dep")
    os.makedirs(SORTIE, exist_ok=True)
    print("départements :", " ".join(deps))
    cles, nombres = {}, {}
    for d in deps:
        t1 = time.time()
        p = preparer(d)
        cles[d], nombres[d] = np.unique(p["k"], return_counts=True)
        print(f"   {d} : {len(p['k'])} bouts de rue gardés sur {int(p['total'][0])}, {len(cles[d])} cases, {int(len(p['plat']))} points utiles ({time.time() - t1:.0f} s)", flush=True)
        del p
    toutes, inv = np.unique(np.concatenate(list(cles.values())), return_inverse=True)
    fichier = decoupage(toutes, np.bincount(inv, weights=np.concatenate(list(nombres.values())), minlength=len(toutes)))
    par_dep = {}                                              # département -> {fichier: [cases de base]}
    for d in deps:
        g = par_dep[d] = {}
        for k in cles[d].tolist():
            g.setdefault(fichier[k], []).append(k)
    reste = {}                                                # fichier -> nombre de départements encore attendus
    for d in deps:
        for f in par_dep[d]:
            reste[f] = reste.get(f, 0) + 1
    attente, ecrits, total, plus_gros = {}, [], 0, 0
    for d in deps:
        p = preparer(d)
        zones = json.load(open(f"out/dep/{d}/zones.json", encoding="utf-8")) if os.path.exists(f"out/dep/{d}/zones.json") else [{}]
        for f, ks in par_dep[d].items():
            attente.setdefault(f, []).append(morceau(p, zones, ks))
            reste[f] -= 1
            if reste[f] == 0:
                nom = "%d_%d_%d.bin" % f
                ecrire(f"{SORTIE}/{nom}", attente.pop(f))
                o = os.path.getsize(f"{SORTIE}/{nom}"); total += o; plus_gros = max(plus_gros, o)
                ecrits.append(f)
        del p
        print(f"   {d} assemblé, {len(ecrits)} tuiles écrites, {len(attente)} en attente", flush=True)
    garder = {"%d_%d_%d.bin" % f for f in ecrits} | {"index.json", "hw.json"}
    for f in os.listdir(SORTIE):
        if f not in garder:
            os.remove(os.path.join(SORTIE, f))
    noms = {c: n for c, n in zip(config.departements().code, config.departements().nom)}
    Path(f"{SORTIE}/index.json").write_text(json.dumps({"ts_lon": TS_LON, "ts_lat": TS_LAT, "t": [v for f in ecrits for v in f],
                                                        "deps": [[d, noms.get(d, d)] for d in deps]}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    Path(f"{SORTIE}/hw.json").write_text(json.dumps(HW))
    niv = np.bincount([f[0] for f in ecrits], minlength=NIVEAU_MAX + 1)
    print(f"{len(ecrits)} tuiles dans {SORTIE} ({len(toutes)} cases de base ; par niveau 0 à {NIVEAU_MAX} : {' '.join(map(str, niv))}) : "
          f"{total / 1e6:.0f} Mo compressés, moyenne {total / len(ecrits) / 1e3:.0f} Ko, la plus grosse {plus_gros / 1e3:.0f} Ko")
    nom = "%d_%d_%d" % ecrits[len(ecrits) // 2]
    t = lire_tuile(f"{SORTIE}/{nom}.bin")
    print(f"contrôle de relecture ({nom}) : {len(t['a'])} bouts de rue, {len(t['id'])} points, bruit {np.nanmin(t['noise']):.1f} à {np.nanmax(t['noise']):.1f} dB, "
          f"{len(t['json']['z']) - 1} zones, {len(t['json']['p'])} points utiles")
    print(f"terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
