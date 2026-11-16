"""
Réglages communs du pipeline Oncyal : quel département est traité, son emprise, où sont ses fichiers.

Le département vient de la variable d'environnement ONCYAL_DEP (« 06 » par défaut) ; mise_a_jour.py la règle
pour chaque département qu'il traite. Chaque étape lit et écrit dans out/dep/<code>/ :
  reseau.csv.gz   une ligne par bout de rue (bruit, air, accès...)
  zones.json      accès incertains
  poi.json        points utiles
  signaux.npy     nœuds à feux
Les routes viennent de l'extraction Geofabrik de l'ancienne région qui contient le département (data/osm).
L'emprise traitée est le rectangle du département élargi de 0,03° (environ 3 km) : les voisins proches comptent
pour le bruit. assemble.py ne garde ensuite, pour chaque département, que les bouts de rue qui lui appartiennent.
"""
import functools, glob, json, os, sys

# Les données de travail (téléchargements dans data/, résultats intermédiaires dans out/ : des gigaoctets) vivent hors
# du dossier du projet, qui est synchronisé par OneDrive : dossier ONCYAL_DONNEES, par défaut « oncyal-donnees » dans le
# dossier personnel. Tout script qui importe config travaille dans ce dossier (chemins relatifs data/... et out/...).
ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.environ.get("ONCYAL_DONNEES") or os.path.join(os.path.expanduser("~"), "oncyal-donnees")
os.makedirs(RACINE, exist_ok=True)
os.chdir(RACINE)

DEP = os.environ.get("ONCYAL_DEP", "06")
DEP3 = DEP.zfill(3)                                   # « 006 » : suffixe des fichiers du Cerema
DOSSIER = f"out/dep/{DEP}"
FICHIER = f"{DOSSIER}/reseau.csv.gz"
ADMIN = "data/admin/departements.geojson"             # contours IGN ADMIN EXPRESS (voir telecharge.py)
MARGE = 0.03

# anciennes régions de Geofabrik -> départements
GEOFABRIK = {
    "alsace": "67 68", "aquitaine": "24 33 40 47 64", "auvergne": "03 15 43 63", "basse-normandie": "14 50 61",
    "bourgogne": "21 58 71 89", "bretagne": "22 29 35 56", "centre": "18 28 36 37 41 45", "champagne-ardenne": "08 10 51 52",
    "corse": "2A 2B", "franche-comte": "25 39 70 90", "haute-normandie": "27 76", "ile-de-france": "75 77 78 91 92 93 94 95",
    "languedoc-roussillon": "11 30 34 48 66", "limousin": "19 23 87", "lorraine": "54 55 57 88",
    "midi-pyrenees": "09 12 31 32 46 65 81 82", "nord-pas-de-calais": "59 62", "pays-de-la-loire": "44 49 53 72 85",
    "picardie": "02 60 80", "poitou-charentes": "16 17 79 86", "provence-alpes-cote-d-azur": "04 05 06 13 83 84",
    "rhone-alpes": "01 07 26 38 42 69 73 74", "guadeloupe": "971", "martinique": "972", "guyane": "973", "reunion": "974",
    "mayotte": "976",
}
REGION = next((r for r, d in GEOFABRIK.items() if DEP in d.split()), None)
ATMOSUD = set("04 05 06 13 83 84".split())           # départements couverts par la modélisation fine d'AtmoSud

# Cartes d'air des autres agences régionales (moyenne annuelle de NO2) : voir telecharge.py.
# « wcs » : serveur GeoServer, couche téléchargée à 25 m ; « tif » : un fichier pour toute la région.
AIR = {
    "Atmo Auvergne-Rhône-Alpes": dict(deps="01 03 07 15 26 38 42 43 63 69 73 74", wcs="https://sig.atmo-auvergnerhonealpes.fr/geoserver/ows",
                                      couche="mod_aura_region_2025__mod_aura_2025_no2_moyan", epsg=2154, pas=10.0),
    "Airparif": dict(deps="75 77 78 91 92 93 94 95", wcs="https://namek.airparif.fr/geoserver/ows",
                     couche="Moyenne_annuelle__NO2_2025_30", epsg=27572, pas=12.5),
    "Atmo Nouvelle-Aquitaine": dict(deps="16 17 19 23 24 33 40 47 64 79 86 87", wcs="https://opendata.atmo-na.org/geoserver/ows",
                                    couche="mod_nouvelle_aquitaine_2025__mod_nouvelle_aquitaine_2025_no2_moya", epsg=2154, pas=10.0),
    "Air Pays de la Loire": dict(deps="44 49 53 72 85", wcs="https://data.airpl.org/geoserver/ows",
                                 couche="mod_pays_de_la_loire_2025__mod_pays_de_la_loire_2025_NO2_Moy", epsg=2154, pas=10.0),
    "Atmo Normandie": dict(deps="14 27 50 61 76", tif="Normandie_Moyenne_annuelle_2025_NO2.tif",
                           capacites="https://api.atmonormandie.fr/index.php/lizmap/service/?repository=hmodelisation&project=mod_normandie_moyenne_annuelle_no2&SERVICE=WMS&REQUEST=GetCapabilities"),
    # « wcs_entier » : carte régionale à maille large (500 m), téléchargée en une fois
    "Atmo Bourgogne-Franche-Comté": dict(deps="21 25 39 58 70 71 89 90", wcs_entier="https://geoserver.atmo-bfc.org/geoserver/ows",
                                         couche="modelisation__mod_bfc_2025_no2_moyan", epsg=3035, annee=2025),
    # Agences qui ne publient que l'image de la carte : valeurs relues d'après les couleurs (voir air_couleurs.py).
    # « export » : serveur ArcGIS dynamique ; « tuiles » : tuiles en cache (z = niveau de zoom) ; « wms » : service WMS.
    "Atmo Hauts-de-France": dict(deps="02 59 60 62 80", export="https://sig.atmo-hdf.fr/server/rest/services/FE_An_NO2/MapServer", couche=7, annee=2025),
    "Atmo Grand Est": dict(deps="08 10 51 52 54 55 57 67 68 88", annee=2025, z=12,
                           tuiles="https://portailsig.atmo-grandest.eu/server/rest/services/Hosted/mod_grandest_2025_no2_moyan/MapServer"),
    "Air Breizh": dict(deps="22 29 35 56", wms="https://datacarto.airbreizh.asso.fr/wms", couche="raster_2023_2023_bzh_NO2_esmAS_moya_2023_WGS84_REG_tif", annee=2023),
    "Lig'Air": dict(deps="18 28 36 37 41 45", wms="https://datacarto.opendata-ligair.fr/wms",
                    couche="mod_centre_val_de_loire_2025_mod_centre_val_de_loire_2025_no2_moyan_tif", annee=2025),
    "Atmo Occitanie": dict(deps="09 11 12 30 31 32 34 46 48 65 66 81 82", annee=2017, z=11, rapport=0.7,
                           tuiles="https://tiles.arcgis.com/tiles/7Sr9Ek9c1QTKmbwr/arcgis/rest/services/mod_occitanie_2017_no2_moyan/MapServer",
                           dessus=[("https://tiles.arcgis.com/tiles/7Sr9Ek9c1QTKmbwr/arcgis/rest/services/mod_ppatoulouse_2025_no2_moyan/MapServer", 12), ("https://tiles.arcgis.com/tiles/7Sr9Ek9c1QTKmbwr/arcgis/rest/services/mod_ppamontpellier_2025_no2_moyan/MapServer", 12),
                                   ("https://tiles.arcgis.com/tiles/7Sr9Ek9c1QTKmbwr/arcgis/rest/services/mod_ppanimes_2025_no2_moyan/MapServer", 12), ("https://tiles.arcgis.com/tiles/7Sr9Ek9c1QTKmbwr/arcgis/rest/services/mod_cuperpignan_2025_no2_moyan/MapServer", 12)]),
    "Qualitair Corse": dict(deps="2A 2B", annee=2025, z=12,
                            tuiles="https://tiles.arcgis.com/tiles/VQopoXNvUqHYZHjY/arcgis/rest/services/2025_NO2_MA_200M_AIRES_tif/MapServer"),
}
# Bruit : départements absents du jeu national du Cerema (métropole du Grand Paris), publiés par la DRIEAT Île-de-France
# sur data.gouv.fr ; fin du titre du lot. Les lots de l'Essonne et du Val-d'Oise complètent ceux du Cerema.
MGP = {"75": "pour Paris", "92": "des Hauts-de-Seine", "93": "de Seine-Saint-Denis", "94": "du Val-de-Marne", "91": "dans l'Essone", "95": "dans le Val-d'-Oise"}


def source_air(dep=None):
    """(nom de l'agence, réglages) pour le département, ou (None, None) s'il n'y a pas de carte d'air téléchargeable."""
    dep = dep or DEP
    if dep in ATMOSUD:
        return "AtmoSud", {}
    return next(((n, c) for n, c in AIR.items() if dep in c["deps"].split()), (None, None))


def air_dir(dep=None):
    dep = dep or DEP
    return f"data/atmosud/{dep}" if dep in ATMOSUD else f"data/air/{dep}"


def zones_bruit(f):
    """Lit une carte de bruit (zones par tranche de 5 dB) : GeoDataFrame en Lambert-93 avec la colonne « lvl ».
    Les fichiers du Cerema nomment la tranche LEGENDE, ceux de la DRIEAT legende ; seule cette colonne est lue
    (certains fichiers ont un champ date illisible)."""
    import geopandas as gpd, pandas as pd, pyogrio
    champs = list(pyogrio.read_info(f)["fields"])
    col = next((c for c in champs if c.upper() == "LEGENDE"), None) or next((c for c in champs if c.lower() == "db_lo"), None)   # RATP : db_lo
    if col is None:
        return None
    g = gpd.read_file(f, columns=[col]).set_crs(2154, allow_override=True)
    g["lvl"] = pd.to_numeric(g[col], errors="coerce")
    g = g[(g.lvl >= 45) & g.geometry.notna() & ~g.geometry.is_empty]      # une tranche « 0 » existe dans certains lots : ignorée
    return g[["lvl", "geometry"]]


def pbf():
    f = sorted(glob.glob(f"data/osm/{REGION}*.osm.pbf"))
    if not f:
        sys.exit(f"extraction OSM de la région {REGION} absente de data/osm : lancer  python telecharge.py {DEP}")
    return f[-1]


@functools.lru_cache(None)
def departements():
    """Contours de tous les départements (GeoDataFrame, WGS84), colonne « code »."""
    import geopandas as gpd
    if not os.path.exists(ADMIN):
        sys.exit(ADMIN + " absent : lancer  python telecharge.py")
    g = gpd.read_file(ADMIN)[["code_insee", "nom_officiel", "geometry"]].rename(columns={"code_insee": "code", "nom_officiel": "nom"})
    return g.reset_index(drop=True)


@functools.lru_cache(None)
def bbox(dep=None):
    """Rectangle (lon min, lat min, lon max, lat max) du département, élargi de MARGE."""
    g = departements()
    b = g[g.code == (dep or DEP)].total_bounds
    return (b[0] - MARGE, b[1] - MARGE, b[2] + MARGE, b[3] + MARGE)


def nom(dep=None):
    g = departements()
    return g[g.code == (dep or DEP)].nom.iloc[0]


def departement_des_points(lon, lat):
    """Code du département de chaque point : celui qui le contient, sinon le plus proche à moins de 5 km
    (mer, Monaco, bout de route qui passe la frontière), sinon une chaîne vide."""
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import box
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    if not len(lon):
        return np.array([], dtype=object)
    g = departements()
    g = g[g.intersects(box(lon.min() - 0.1, lat.min() - 0.1, lon.max() + 0.1, lat.max() + 0.1))].reset_index(drop=True)
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon, lat), crs=4326)
    j = gpd.sjoin(pts, g[["code", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    code = j.code.reindex(range(len(pts))).values.astype(object)
    manque = np.array([c is None or c != c for c in code])
    if manque.any():
        gl, pl = g.to_crs(2154), pts[manque].to_crs(2154)
        k = gpd.sjoin_nearest(pl, gl[["code", "geometry"]], how="left", max_distance=5000)
        k = k[~k.index.duplicated(keep="first")]
        code[np.where(manque)[0]] = k.code.reindex(pl.index).values
    return np.array(["" if (c is None or c != c) else c for c in code], dtype=object)
