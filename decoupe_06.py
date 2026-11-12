"""
Découpe out/reseau_06.csv.gz en petits fichiers binaires par zone (~4 x 5,5 km) dans out/tuiles/.
Chaque fichier contient les points (nœuds) et les bouts de rue d'une zone, valeurs compressées sur 1 octet.
Lancer :  python decoupe_06.py
Le fichier out/tuiles/index.json liste les zones ; lire_tuile() relit un fichier (sert aussi de contrôle).
"""
import gzip, json, os, struct, sys, zlib
from pathlib import Path
import numpy as np
import pandas as pd

FICHIER = "out/reseau_06.csv.gz"
DOSSIER = "out/tuiles"
TS_LON, TS_LAT = 0.05, 0.04        # taille d'une zone en degrés
MAGIC = b"CC01"
NA = 255                            # « pas de donnée » pour les valeurs sur 1 octet


def q(v, echelle, decalage=0.0):
    """Valeur -> octet 0..254 ; 255 = pas de donnée."""
    v = np.asarray(v, dtype=float)
    o = np.clip(np.round((v - decalage) * echelle), 0, 254)
    o[~np.isfinite(v)] = NA
    return o.astype(np.uint8)


def ecrire_tuile(chemin, e):
    ids = np.concatenate([e.a.values, e.b.values])
    lon = np.concatenate([e.alon.values, e.blon.values])
    lat = np.concatenate([e.alat.values, e.blat.values])
    noeuds, premier, inv = np.unique(ids, return_index=True, return_inverse=True)
    m = len(e)
    ia, ib = inv[:m].astype(np.uint32), inv[m:].astype(np.uint32)
    longueur = np.clip(np.round(e.len_m.values * 10), 0, 65535).astype(np.uint16)       # dixièmes de mètre
    flags = ((e.oneway.values + 1) | ((e.lit.values + 1) << 2) | (e.noise_src.values << 4)).astype(np.uint8)
    blocs = [
        np.asarray(noeuds, dtype="<f8"),
        np.round(lon[premier] * 1e6).astype("<i4"), np.round(lat[premier] * 1e6).astype("<i4"),
        ia.astype("<u4"), ib.astype("<u4"), longueur.astype("<u2"),
        e.hw.values.astype(np.uint8), flags,
        q(e.noise.values, 4, 30),            # dB   : (dB - 30) x 4   -> pas de 0,25 dB
        q(e.no2_moyan.values, 2),            # µg/m3 x 2
        q(e.pm10_moyan.values, 1),           # µg/m3 x 1
        q(e.pm25_moyan.values, 2),           # µg/m3 x 2
        q(e.icair365.values, 10),            # indice x 10
        q(e.lum_nasa.values, 254),           # 0..1 x 254
        # accès OSM (voir acces_06.py), placé en dernier : une ancienne page l'ignore sans erreur
        (e.acc.values if "acc" in e else np.full(m, 4)).astype(np.uint8),
    ]
    corps = b"".join(b.tobytes() for b in blocs)
    # compressé en gzip : Cloudflare ne compresse pas les fichiers binaires, la page les décompresse elle-même
    Path(chemin).write_bytes(gzip.compress(MAGIC + struct.pack("<II", len(noeuds), m) + corps, compresslevel=9, mtime=0))
    return len(corps) + 12


def lire_tuile(chemin):
    d = Path(chemin).read_bytes()
    if d[:2] == b"\x1f\x8b":
        d = gzip.decompress(d)
    assert d[:4] == MAGIC, "fichier invalide"
    n, m = struct.unpack("<II", d[4:12])
    p = 12
    def lire(dt, k):
        nonlocal p
        a = np.frombuffer(d, dtype=dt, count=k, offset=p); p += a.nbytes; return a
    t = {"id": lire("<f8", n), "lon": lire("<i4", n) / 1e6, "lat": lire("<i4", n) / 1e6,
         "a": lire("<u4", m), "b": lire("<u4", m), "len_m": lire("<u2", m) / 10.0,
         "hw": lire("u1", m), "flags": lire("u1", m)}
    for nom, echelle, dec in (("noise", 4, 30), ("no2", 2, 0), ("pm10", 1, 0), ("pm25", 2, 0), ("icair", 10, 0), ("lum", 254, 0)):
        o = lire("u1", m).astype(float)
        t[nom] = np.where(o == NA, np.nan, o / echelle + dec)
    if p + m <= len(d):
        t["acc"] = lire("u1", m)
    t["oneway"] = (t["flags"] & 3).astype(int) - 1
    t["lit"] = ((t["flags"] >> 2) & 3).astype(int) - 1
    t["noise_src"] = (t["flags"] >> 4) & 1
    return t


def main():
    if not os.path.exists(FICHIER):
        sys.exit(FICHIER + " introuvable")
    e = pd.read_csv(FICHIER)
    print("réseau lu :", len(e), "bouts de rue")
    if e.len_m.max() > 6553:
        print("attention :", int((e.len_m > 6553).sum()), "bouts de rue dépassent 6,5 km (longueur plafonnée)")
    os.makedirs(DOSSIER, exist_ok=True)
    ix = np.floor(((e.alon + e.blon) / 2) / TS_LON).astype(int).values
    iy = np.floor(((e.alat + e.blat) / 2) / TS_LAT).astype(int).values
    cle = (ix * 100000 + iy)
    ordre = np.argsort(cle, kind="stable")
    cles, debut = np.unique(cle[ordre], return_index=True)
    fins = np.append(debut[1:], len(ordre))
    index, total_brut, total_gz, plus_gros = [], 0, 0, 0
    for c, d, f in zip(cles, debut, fins):
        sel = ordre[d:f]
        x, y = int(c // 100000), int(c % 100000)
        nom = f"{x}_{y}.bin"
        brut = ecrire_tuile(f"{DOSSIER}/{nom}", e.iloc[sel])
        gz = os.path.getsize(f"{DOSSIER}/{nom}")
        total_brut += brut; total_gz += gz; plus_gros = max(plus_gros, gz)
        index.append({"x": x, "y": y, "aretes": int(f - d), "octets_gz": gz})
    Path(f"{DOSSIER}/index.json").write_text(json.dumps({"ts_lon": TS_LON, "ts_lat": TS_LAT, "tuiles": index}))
    print(f"{len(index)} fichiers dans {DOSSIER}")
    print(f"taille totale : {total_brut / 1e6:.0f} Mo brut, {total_gz / 1e6:.0f} Mo compressés (fichiers écrits en gzip)")
    print(f"fichier moyen : {total_gz / len(index) / 1e3:.0f} Ko compressé | le plus gros : {plus_gros / 1e3:.0f} Ko")
    # contrôle : un fichier relu doit redonner exactement les valeurs d'origine
    x, y = index[len(index) // 2]["x"], index[len(index) // 2]["y"]
    t = lire_tuile(f"{DOSSIER}/{x}_{y}.bin")
    print(f"contrôle de relecture ({x}_{y}) : {len(t['a'])} bouts de rue, {len(t['id'])} points, "
          f"bruit {np.nanmin(t['noise']):.1f} à {np.nanmax(t['noise']):.1f} dB, NO2 {np.nanmin(t['no2']):.1f} à {np.nanmax(t['no2']):.1f}")


if __name__ == "__main__":
    main()
