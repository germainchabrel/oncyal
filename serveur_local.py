"""
Serveur local pour essayer le site avant de publier : il sert le dossier site/ du projet et prend les données
(tuiles/) directement dans le dossier de travail (out/tuiles, hors du projet : voir config.py), sans rien copier.

Lancer :  python serveur_local.py          puis ouvrir http://localhost:8000
          (tests de référence : http://localhost:8000/#tests)
"""
import functools, http.server, os, sys
import config

SITE = os.path.join(config.ICI, "site")
TUILES = os.path.join(config.RACINE, "out", "tuiles")


class Page(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = path.split("?", 1)[0].split("#", 1)[0]
        if p.startswith("/tuiles/"):
            return os.path.join(TUILES, os.path.basename(p))
        return super().translate_path(path)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"http://localhost:{port}  (page : {SITE} ; données : {TUILES})", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Page, directory=SITE)).serve_forever()
