"""
Mise à jour des données d'Oncyal, département par département.

  python mise_a_jour.py 83 13          traite ces départements, puis réassemble tout le site
  python mise_a_jour.py --tous         retraite tous les départements déjà présents dans out/dep
  python mise_a_jour.py --assembler    réassemble seulement (out/tuiles -> site/tuiles)
  option --osm-neuf                    retélécharge d'abord la dernière extraction OpenStreetMap de la région

Les données de travail (data/, out/) sont dans le dossier « oncyal-donnees » du dossier personnel, hors du projet
(voir config.py). Pour chaque département, dans l'ordre :
  0. telecharge.py          routes OSM de la région, cartes de bruit du Cerema, air AtmoSud (région PACA)
  1. prepare.py             routes OSM + bruit Cerema + air
  2. bruit_complement.py    bruit estimé là où le Cerema ne couvre pas
  3. nuit.py                bruit de nuit (Lnight du Cerema)
  4. avions.py              bruit des aérodromes (plans d'exposition au bruit)
  5. acces.py               voies privées, sens uniques vélo, barrières
  6. zones.py               accès incertains : horaires d'ouverture, enceintes, parcs
  7. accidents.py           accidents de vélo 2020-2024 (ONISR)
  8. signaux.py             feux tricolores
  9. poi.py                 fontaines, arceaux, ateliers, magasins
Puis, une fois pour tous :
  assemble.py               tuiles du site (out/tuiles), tous départements confondus
  nouvelle VERSION dans site/sw.js (vide l'ancien cache hors ligne)
Un département qui échoue est signalé et laissé de côté ; les autres continuent.
Ensuite : vérifier le site en local (python serveur_local.py, puis http://localhost:8000/#tests), puis publier :
la page (dossier site, sans tuiles) et les tuiles (out/tuiles du dossier de travail) sont copiées vers
Downloads\\oncyal, puis npx wrangler deploy. Les trois commandes sont affichées à la fin de l'assemblage.
"""
import datetime, glob, os, re, shutil, subprocess, sys, time
import config          # données de travail dans config.RACINE (hors du dossier du projet)

ICI = os.path.dirname(os.path.abspath(__file__))
DONNEES = config.RACINE
PY = sys.executable
ETAPES = ["prepare.py", "bruit_complement.py", "nuit.py", "avions.py", "acces.py", "zones.py", "accidents.py", "signaux.py", "poi.py"]


def traiter(dep, neuf):
    env = dict(os.environ, ONCYAL_DEP=dep, PYTHONIOENCODING="utf-8")
    t0 = time.time()
    os.makedirs(os.path.join(DONNEES, "out", "dep", dep), exist_ok=True)
    journal = open(os.path.join(DONNEES, "out", "dep", dep, "journal.txt"), "w", encoding="utf-8")
    for e in ["telecharge.py"] + ETAPES:
        print(f"[{dep}] {e}", flush=True)
        args = [PY, e] + ([dep] + (["--osm-neuf"] if neuf else []) if e == "telecharge.py" else [])
        r = subprocess.run(args, cwd=ICI, env=env, stdout=journal, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            print(f"[{dep}] ÉCHEC à l'étape {e} : voir {DONNEES}/out/dep/{dep}/journal.txt", flush=True)
            # un réseau incomplet ne doit pas entrer dans le site
            f = os.path.join(DONNEES, "out", "dep", dep, "reseau.csv.gz")
            if os.path.exists(f):
                os.replace(f, f + ".echec")
            return False
    print(f"[{dep}] terminé en {(time.time() - t0) / 60:.1f} min", flush=True)
    return True


def assembler():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    print("\n===== assemble.py =====", flush=True)
    if subprocess.run([PY, "assemble.py"], cwd=ICI, env=env).returncode != 0:
        sys.exit("échec de l'assemblage : le site n'a pas été touché.")
    # les tuiles restent dans le dossier de travail (plusieurs centaines de Mo : pas dans le projet, que OneDrive synchronise)
    src = os.path.join(DONNEES, "out", "tuiles")
    sw = os.path.join(ICI, "site", "sw.js")
    texte = open(sw, encoding="utf-8").read()
    version = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    texte = re.sub(r"var VERSION = '[^']*'", f"var VERSION = 'oncyal-{version}'", texte)
    open(sw, "w", encoding="utf-8", newline="").write(texte)
    print(f"tuiles prêtes dans {src} ({len(os.listdir(src))} fichiers), cache hors ligne : oncyal-{version}")
    print("essai en local :  python serveur_local.py   puis http://localhost:8000/#tests")
    print("publication, en trois commandes (PowerShell) :")
    print(f'  robocopy "{os.path.join(ICI, "site")}" "$env:USERPROFILE\\Downloads\\oncyal" /MIR /XD tuiles')
    print(f'  robocopy "{src}" "$env:USERPROFILE\\Downloads\\oncyal\\tuiles" /MIR')
    print("  npx wrangler deploy      (depuis le dossier personnel)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--tous" in sys.argv:
        args = sorted(os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(DONNEES, "out", "dep", "*", "reseau.csv.gz")))
    t0, rates = time.time(), []
    for dep in args:
        if not traiter(dep, "--osm-neuf" in sys.argv):
            rates.append(dep)
    if "--sans-assembler" not in sys.argv:
        assembler()
    print(f"\ntout est fini en {(time.time() - t0) / 60:.0f} min" + (f" ; départements en échec : {' '.join(rates)}" if rates else ""))


if __name__ == "__main__":
    main()
