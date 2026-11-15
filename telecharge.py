"""
Télécharge les données sources d'un ou plusieurs départements (ce qui est déjà là n'est pas retéléchargé) :
  - contours des départements : IGN ADMIN EXPRESS (service WFS de la Géoplateforme)      -> data/admin
  - routes : extraction OpenStreetMap de l'ancienne région, chez Geofabrik (ODbL)         -> data/osm
  - bruit : cartes de bruit stratégiques 2022 du Cerema, un zip par département,
            jeu « Cartes de bruit stratégiques des réseaux routiers et ferroviaires non concédés »
            sur data.gouv.fr (Licence Ouverte)                                            -> data/cerema
  - bruit du Grand Paris (75, 92, 93, 94, communes de la métropole en 91 et 95) : lots de la DRIEAT
            Île-de-France sur data.gouv.fr, même format que le Cerema (Licence Ouverte)   -> data/cerema/mgp-<code>
  - air : moyenne annuelle de NO2 de l'agence régionale, quand elle publie ses valeurs (licence ODbL) :
          AtmoSud (WCS, 25 m)                                                             -> data/atmosud/<code>
          Atmo Auvergne-Rhône-Alpes, Airparif, Atmo Nouvelle-Aquitaine, Air Pays de la Loire
          (WCS à 10 ou 12,5 m, téléchargé à 25 m), Atmo Normandie (fichier GeoTIFF à 25 m) -> data/air/<code>
Les accidents (ONISR) et les plans d'exposition au bruit des aérodromes (DGAC) sont des fichiers nationaux,
déjà dans data/accidents et data/avions.
Lancer :  python telecharge.py 83 13        (--osm-neuf pour reprendre la dernière extraction OSM)
          python telecharge.py --prealable 69 75 76     seulement les gros fichiers communs (routes des régions,
                                                        carte d'air de Normandie), à faire avant de traiter
                                                        plusieurs départements en parallèle
"""
import glob, html, io, json, os, re, sys, time, zipfile
import numpy as np
import requests
import config          # place le script dans le dossier des données de travail

UA = {"User-Agent": "oncyal-pipeline"}
WFS_DEP = ("https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
           "&TYPENAMES=ADMINEXPRESS-COG-CARTO.LATEST:departement&OUTPUTFORMAT=application/json&SRSNAME=EPSG:4326")
CEREMA = "https://www.data.gouv.fr/api/1/datasets/cartes-de-bruit-strategiques-des-reseaux-routiers-et-ferroviaires-non-concedes-directive-europeenne-2002-49-ce/"
ATMOSUD = "https://geoservices.atmosud.org/geoserver/mod_sudpaca_2024/wcs"
DRIEAT = "6511605c27356de83427f4cb"          # organisation « DRIEAT Île-de-France » sur data.gouv.fr
GX0, GY1, PAS, NX, NY, BLOC = 795487.5, 6454512.5, 25.0, 11521, 9841, 1000      # grille AtmoSud (Lambert-93)


def http(url, essais=6, **kw):
    """requests.get qui réessaie : sur une longue série de téléchargements, les coupures passagères sont fréquentes."""
    kw.setdefault("headers", UA); kw.setdefault("timeout", 300)
    for i in range(essais):
        try:
            r = requests.get(url, **kw); r.raise_for_status(); return r
        except Exception as ex:
            if i == essais - 1:
                raise
            print(f"   nouvel essai ({type(ex).__name__})", flush=True); time.sleep(15 * (i + 1))


def fichier(url, cible):
    """Gros fichier. Avec curl quand il est installé : reprise après coupure, et dix fois plus rapide que requests
    sur le serveur de Geofabrik (constaté le 15 novembre 2026). Sinon avec requests."""
    import shutil, subprocess
    os.makedirs(os.path.dirname(cible), exist_ok=True)
    if shutil.which("curl"):
        if subprocess.run(["curl", "-sL", "--retry", "8", "--retry-delay", "10", "-C", "-", "-o", cible + ".part", url]).returncode != 0:
            sys.exit("échec du téléchargement : " + url)
    else:
        with requests.get(url, stream=True, timeout=300, headers=UA) as r:
            r.raise_for_status()
            with open(cible + ".part", "wb") as f:
                for bloc in r.iter_content(1 << 20):
                    f.write(bloc)
    os.replace(cible + ".part", cible)


def admin():
    import config
    if not os.path.exists(config.ADMIN):
        print("contours des départements (IGN)..."); fichier(WFS_DEP, config.ADMIN)


def osm(region, neuf=False):
    deja = sorted(glob.glob(f"data/osm/{region}*.osm.pbf"))
    if deja and not neuf:
        return deja[-1]
    cible = f"data/osm/{region}-{time.strftime('%y%m%d')}.osm.pbf"
    url = f"https://download.geofabrik.de/europe/france/{region}-latest.osm.pbf"
    print("routes OSM :", url, flush=True)
    fichier(url, cible)
    os.makedirs("sauvegardes/osm_ancien", exist_ok=True)
    for f in deja:
        if os.path.abspath(f) != os.path.abspath(cible):
            os.replace(f, "sauvegardes/osm_ancien/" + os.path.basename(f))
    return cible


_liste_cerema = None


def mgp(dep):
    """Cartes de bruit de la métropole du Grand Paris (lot de la DRIEAT sur data.gouv.fr)."""
    import config
    d3, dos = dep.zfill(3), f"data/cerema/mgp-{dep.zfill(3)}"
    if dep not in config.MGP or os.path.isdir(dos):
        return
    r = http("https://www.data.gouv.fr/api/1/datasets/", params={"organization": DRIEAT, "q": "bruit", "page_size": 50}, timeout=90, headers=UA).json()
    lot = next((x for x in r.get("data", []) if "bruit stratégiques" in x["title"] and x["title"].strip().endswith(config.MGP[dep])), None)
    url = next((z["url"] for z in (lot or {}).get("resources", []) if "atom.geo-ide.developpement-durable" in str(z.get("url"))), None)
    if not url:
        print(f"bruit Grand Paris : lot introuvable pour le département {dep}"); return
    print("bruit Grand Paris :", lot["title"][-45:], flush=True)
    z = zipfile.ZipFile(io.BytesIO(http(url, timeout=900, headers=UA).content))
    z.extractall(dos + ".part")
    os.replace(dos + ".part", dos)


def cerema(dep):
    global _liste_cerema
    d3 = dep.zfill(3)
    mgp(dep)
    if os.path.isdir(f"data/cerema/cbs2022-departement-{d3}"):
        return True
    if _liste_cerema is None:
        _liste_cerema = http(CEREMA, timeout=60, headers=UA).json()["resources"]
    r = next((x for x in _liste_cerema if x["url"].lower().endswith(f"departement-{d3.lower()}.zip")), None)
    if not r:
        if not os.path.isdir(f"data/cerema/mgp-{d3}"):
            print(f"bruit : aucune carte pour le département {dep} (bruit estimé d'après les routes)")
        return False
    print("bruit Cerema :", r["url"], flush=True)
    z = zipfile.ZipFile(io.BytesIO(http(r["url"], timeout=600, headers=UA).content))
    z.extractall(f"data/cerema/cbs2022-departement-{d3}.part")          # extraction complète avant de donner le nom définitif
    os.replace(f"data/cerema/cbs2022-departement-{d3}.part", f"data/cerema/cbs2022-departement-{d3}")
    return True


def atmosud(dep, couches=("no2_moyan", "icair365")):
    import config, logging, tifffile
    from pyproj import Transformer
    logging.getLogger("tifffile").setLevel(logging.ERROR)      # la valeur « pas de donnée » des fichiers AtmoSud déclenche un avertissement sans conséquence
    dos = f"data/atmosud/{dep}"
    if all(os.path.exists(f"{dos}/{c}.npy") for c in couches):
        return
    os.makedirs(dos, exist_ok=True)
    lo0, la0, lo1, la1 = config.bbox(dep)
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    pts = [tr.transform(lon, lat) for lon in (lo0, lo1) for lat in (la0, la1)]
    xmin, xmax, ymin, ymax = min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts)
    c0, c1 = max(0, int((xmin - GX0) // PAS)), min(NX, int(-(-(xmax - GX0) // PAS)))
    r0, r1 = max(0, int((GY1 - ymax) // PAS)), min(NY, int(-(-(GY1 - ymin) // PAS)))
    for nom in couches:
        if os.path.exists(f"{dos}/{nom}.npy"):
            continue
        t0 = time.time()
        arr = np.full((r1 - r0, c1 - c0), np.nan, dtype=np.float32)
        for rb in range(r0, r1, BLOC):
            re_ = min(rb + BLOC, r1)
            for cb in range(c0, c1, BLOC):
                ce = min(cb + BLOC, c1)
                params = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"),
                          ("coverageId", f"mod_sudpaca_2024__mod_sudpaca_2024_{nom}"), ("format", "image/tiff"),
                          ("subset", f"X({GX0 + PAS * cb + 5},{GX0 + PAS * ce - 5})"), ("subset", f"Y({GY1 - PAS * re_ + 5},{GY1 - PAS * rb - 5})")]
                for essai in range(4):
                    try:
                        r = http(ATMOSUD, params=params, timeout=300, headers=UA); r.raise_for_status(); break
                    except Exception as ex:
                        print("   nouvel essai :", ex, flush=True); time.sleep(8)
                else:
                    sys.exit("échec du téléchargement AtmoSud")
                a = np.squeeze(tifffile.imread(io.BytesIO(r.content))).astype(np.float32)
                if a.shape != (re_ - rb, ce - cb):
                    sys.exit(f"AtmoSud : taille reçue {a.shape} au lieu de {(re_ - rb, ce - cb)}")
                a[a < -1e30] = np.nan
                arr[rb - r0:re_ - r0, cb - c0:ce - c0] = a
        np.save(f"{dos}/{nom}.npy", arr)
        json.dump(dict(x0=GX0 + PAS * c0, y1=GY1 - PAS * r0, pas=PAS, lignes=r1 - r0, colonnes=c1 - c0, crs="EPSG:2154"), open(f"{dos}/{nom}.json", "w"))
        v = arr[np.isfinite(arr)]
        print(f"air AtmoSud {dep} {nom} : {arr.shape[0]} x {arr.shape[1]} cases, {100 * v.size / arr.size:.0f} % valides, moyenne {v.mean():.1f} ({time.time() - t0:.0f} s)", flush=True)


def lire_tiff(octets):
    import logging, tifffile
    logging.getLogger("tifffile").setLevel(logging.ERROR)
    return np.squeeze(tifffile.imread(io.BytesIO(octets))).astype(np.float32)


def propre(a):
    """Valeurs « pas de donnée » et valeurs absurdes (quelques cases à plusieurs centaines de µg/m3 chez Atmo AURA) retirées."""
    a = a.astype(np.float32)
    a[~np.isfinite(a) | (a <= 0) | (a > 200)] = np.nan
    return a


def air_wcs(dep, nom, c):
    """NO2 annuel d'une agence régionale par WCS, ramené à 25 m (scalefactor), par blocs de 25 km calés sur la grille d'origine."""
    import config
    from pyproj import Transformer
    dos = config.air_dir(dep)
    if os.path.exists(f"{dos}/no2_moyan.npy"):
        return
    os.makedirs(dos, exist_ok=True)
    d = http(c["wcs"], params={"service": "WCS", "version": "2.0.1", "request": "DescribeCoverage", "coverageId": c["couche"]}, timeout=120, headers=UA).text
    gx0, gy0 = map(float, re.search(r"<gml:lowerCorner>([^<]+)<", d).group(1).split())
    gx1, gy1 = map(float, re.search(r"<gml:upperCorner>([^<]+)<", d).group(1).split())
    pas, fac = c["pas"], c["pas"] / 25.0
    NX, NY = int(round((gx1 - gx0) / pas)), int(round((gy1 - gy0) / pas))
    B = int(round(1000 / fac))                                                    # bloc de 25 km, en cases d'origine
    k = next(i for i in range(1, 100) if abs(i * fac - round(i * fac)) < 1e-9)   # calage : k cases d'origine = un nombre entier de cases de 25 m
    lo0, la0, lo1, la1 = config.bbox(dep)
    tr = Transformer.from_crs(4326, c["epsg"], always_xy=True)
    pts = [tr.transform(lon, lat) for lon in (lo0, lo1) for lat in (la0, la1)]
    xmin, xmax, ymin, ymax = min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts)
    c0, c1 = max(0, int((xmin - gx0) // pas)), min(NX, int(-(-(xmax - gx0) // pas)))
    r0, r1 = max(0, int((gy1 - ymax) // pas)), min(NY, int(-(-(gy1 - ymin) // pas)))
    if c0 >= c1 or r0 >= r1:
        print(f"air {nom} : le département {dep} est hors de la carte"); return
    def debuts(a0, a1, N):                       # débuts de blocs (cases d'origine), le dernier ramené dans la grille
        fin = (max(0, N - B) // k) * k
        return sorted({min(b, fin) for b in range((a0 // B) * B, a1, B)})
    cols, ligs = debuts(c0, c1, NX), debuts(r0, r1, NY)
    cmin, rmin = cols[0], ligs[0]
    W, H = int(round((cols[-1] + B - cmin) * fac)), int(round((ligs[-1] + B - rmin) * fac))
    arr = np.full((H, W), np.nan, dtype=np.float32)
    t0, n = time.time(), 0
    for rb in ligs:
        for cb in cols:
            xa, xb = gx0 + pas * cb + pas / 2, gx0 + pas * min(cb + B, NX) - pas / 2
            ya, yb = gy1 - pas * min(rb + B, NY) + pas / 2, gy1 - pas * rb - pas / 2
            params = [("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"), ("coverageId", c["couche"]), ("format", "image/tiff"),
                      ("subset", f"X({xa},{xb})"), ("subset", f"Y({ya},{yb})"), ("scalefactor", str(fac))]
            for essai in range(5):
                try:
                    r = http(c["wcs"], params=params, timeout=600, headers=UA); r.raise_for_status()
                    a = propre(lire_tiff(r.content)); break
                except Exception as ex:
                    print("   nouvel essai :", type(ex).__name__, str(ex)[:80], flush=True); time.sleep(15)
            else:
                sys.exit(f"échec du téléchargement de l'air ({nom})")
            i, j = int(round((rb - rmin) * fac)), int(round((cb - cmin) * fac))
            h, w = min(a.shape[0], H - i), min(a.shape[1], W - j)
            arr[i:i + h, j:j + w] = a[:h, :w]
            n += 1
    np.save(f"{dos}/no2_moyan.npy", arr)
    json.dump(dict(x0=gx0 + pas * cmin, y1=gy1 - pas * rmin, pas=25.0, lignes=H, colonnes=W, crs=f"EPSG:{c['epsg']}", source=nom, couche=c["couche"]), open(f"{dos}/no2_moyan.json", "w"))
    v = arr[np.isfinite(arr)]
    print(f"air {nom} {dep} : {H} x {W} cases de 25 m en {n} blocs, {100 * v.size / arr.size:.0f} % valides, NO2 moyen {v.mean():.1f}, max {v.max():.0f} ({time.time() - t0:.0f} s)", flush=True)


def air_tif_region(nom, c):
    """Fichier régional (Atmo Normandie) : téléchargé une fois dans data/air."""
    cible = "data/air/" + c["tif"]
    if not os.path.exists(cible):
        cap = http(c["capacites"], timeout=120, headers=UA).text
        url = next((html.unescape(u) for u in re.findall(r"https?://[^\"'<> ]+\.tif", cap) if c["tif"] in html.unescape(u).replace("%2F", "/")), None)
        if not url:
            sys.exit(f"air {nom} : lien du fichier {c['tif']} introuvable")
        print("air", nom, ":", c["tif"], flush=True)
        fichier(url, cible)
    return cible


def air_tif(dep, nom, c):
    import config, tifffile
    from pyproj import Transformer
    dos = config.air_dir(dep)
    if os.path.exists(f"{dos}/no2_moyan.npy"):
        return
    os.makedirs(dos, exist_ok=True)
    chemin = air_tif_region(nom, c)
    with tifffile.TiffFile(chemin) as t:
        p = t.pages[0]
        pas = float(p.geotiff_tags["ModelPixelScale"][0])
        tp = p.geotiff_tags["ModelTiepoint"]
        gx0, gy1 = float(tp[3]) - float(tp[0]) * pas, float(tp[4]) + float(tp[1]) * pas
    # le fichier est compressé en LZW : tifffile ne le lit qu'avec le module imagecodecs, Pillow le lit seul
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(chemin) as im:
        a = np.asarray(im, dtype=np.float32)
    lo0, la0, lo1, la1 = config.bbox(dep)
    tr = Transformer.from_crs(4326, 2154, always_xy=True)
    pts = [tr.transform(lon, lat) for lon in (lo0, lo1) for lat in (la0, la1)]
    xmin, xmax, ymin, ymax = min(q[0] for q in pts), max(q[0] for q in pts), min(q[1] for q in pts), max(q[1] for q in pts)
    c0, c1 = max(0, int((xmin - gx0) // pas)), min(a.shape[1], int(-(-(xmax - gx0) // pas)))
    r0, r1 = max(0, int((gy1 - ymax) // pas)), min(a.shape[0], int(-(-(gy1 - ymin) // pas)))
    arr = propre(np.squeeze(a)[r0:r1, c0:c1])
    np.save(f"{dos}/no2_moyan.npy", arr)
    json.dump(dict(x0=gx0 + pas * c0, y1=gy1 - pas * r0, pas=pas, lignes=arr.shape[0], colonnes=arr.shape[1], crs="EPSG:2154", source=nom, couche=c["tif"]), open(f"{dos}/no2_moyan.json", "w"))
    v = arr[np.isfinite(arr)]
    print(f"air {nom} {dep} : {arr.shape[0]} x {arr.shape[1]} cases de {pas:.0f} m, {100 * v.size / max(arr.size, 1):.0f} % valides, NO2 moyen {v.mean():.1f}, max {v.max():.0f}", flush=True)


def air(dep):
    import config
    nom, c = config.source_air(dep)
    if nom == "AtmoSud":
        atmosud(dep)
    elif nom and "wcs" in c:
        air_wcs(dep, nom, c)
    elif nom:
        air_tif(dep, nom, c)


def region_de(dep):
    import config
    region = next((r for r, d in config.GEOFABRIK.items() if dep in d.split()), None)
    if not region:
        sys.exit(f"département inconnu : {dep}")
    return region


def tout(dep, neuf=False):
    admin()
    osm(region_de(dep), neuf)
    cerema(dep)
    air(dep)


def prealable(deps, neuf=False):
    """Les gros fichiers communs à plusieurs départements, pour que des traitements en parallèle ne les téléchargent pas deux fois."""
    import config
    admin()
    for region in sorted({region_de(d) for d in deps}):
        osm(region, neuf)
    for nom, c in config.AIR.items():
        if "tif" in c and any(d in c["deps"].split() for d in deps):
            air_tif_region(nom, c)


if __name__ == "__main__":
    deps = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not deps:
        admin()
    elif "--prealable" in sys.argv:
        prealable(deps, "--osm-neuf" in sys.argv)
    else:
        for d in deps:
            tout(d, "--osm-neuf" in sys.argv)
