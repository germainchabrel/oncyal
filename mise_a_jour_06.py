"""
Mise à jour complète des données d'Oncyal 06 (à lancer chaque trimestre, ou quand OpenStreetMap a bien changé).

  python mise_a_jour_06.py                 enchaîne tout le pipeline avec le fichier OSM déjà présent
  python mise_a_jour_06.py --telecharger   télécharge d'abord la dernière extraction OSM de la région (Geofabrik, ~400 Mo)

Étapes, dans l'ordre :
  1. prepare_06.py            routes OSM + bruit Cerema + air AtmoSud
  2. lumiere_06.py            lumière satellite NASA
  3. bruit_complement_06.py   bruit estimé là où le Cerema ne couvre pas
  3b. nuit_06.py              bruit de nuit (Lnight du Cerema)
  4. acces_06.py              voies privées, sens uniques vélo, barrières
  5. zones_06.py              accès incertains : horaires d'ouverture, enceintes, parcs (out/tuiles/zones.json)
  5b. signaux_06.py           feux tricolores (out/signaux.npy)
  6. decoupe_06.py            tuiles compressées (out/tuiles)
  7. poi_06.py                fontaines, arceaux, ateliers, magasins (out/tuiles/poi.json)
  8. copie de out/tuiles vers site/tuiles, et nouvelle VERSION dans site/sw.js (vide l'ancien cache hors ligne)
Ensuite : vérifier le site en local, puis publier (robocopy vers Downloads\\oncyal, puis npx wrangler deploy).

Bruit : quand le Cerema publiera les cartes de bruit stratégiques suivantes (échéance 2027), remplacer les fichiers
de data/cerema par les nouveaux avant de lancer ce script.
"""
import datetime, glob, os, re, shutil, subprocess, sys, time

ICI = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
URL_OSM = "https://download.geofabrik.de/europe/france/provence-alpes-cote-d-azur-latest.osm.pbf"
ETAPES = ["prepare_06.py", "lumiere_06.py", "bruit_complement_06.py", "nuit_06.py", "acces_06.py", "zones_06.py", "signaux_06.py", "decoupe_06.py", "poi_06.py"]


def telecharger():
    import requests
    jour = datetime.date.today().strftime("%y%m%d")
    cible = os.path.join(ICI, "data", "osm", f"provence-alpes-cote-d-azur-{jour}.osm.pbf")
    print("téléchargement de", URL_OSM)
    with requests.get(URL_OSM, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(cible + ".part", "wb") as f:
            for bloc in r.iter_content(1 << 20):
                f.write(bloc)
    os.replace(cible + ".part", cible)
    # les scripts prennent le premier fichier .pbf trouvé : les anciens sont rangés à part
    ancien = os.path.join(ICI, "sauvegardes", "osm_ancien"); os.makedirs(ancien, exist_ok=True)
    for p in glob.glob(os.path.join(ICI, "data", "**", "*.pbf"), recursive=True):
        if os.path.abspath(p) != os.path.abspath(cible):
            shutil.move(p, os.path.join(ancien, os.path.basename(p)))
    print("fichier OSM :", cible)


def main():
    t0 = time.time()
    if "--telecharger" in sys.argv:
        telecharger()
    for e in ETAPES:
        print(f"\n===== {e} =====", flush=True)
        if subprocess.run([PY, e], cwd=ICI).returncode != 0:
            sys.exit(f"échec à l'étape {e} : rien n'a été copié vers site/.")
    print("\n===== copie vers site/tuiles =====")
    src, dst = os.path.join(ICI, "out", "tuiles"), os.path.join(ICI, "site", "tuiles")
    for f in os.listdir(dst):
        if not os.path.exists(os.path.join(src, f)):
            os.remove(os.path.join(dst, f))
    for f in os.listdir(src):
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    sw = os.path.join(ICI, "site", "sw.js")
    texte = open(sw, encoding="utf-8").read()
    version = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    texte = re.sub(r"var VERSION = 'oncyal-[^']*';", "var VERSION = 'oncyal-" + version + "';", texte)
    open(sw, "w", encoding="utf-8").write(texte)
    print(f"\nterminé en {(time.time() - t0) / 60:.0f} min. Vérifiez le site en local, puis publiez.")


if __name__ == "__main__":
    main()
