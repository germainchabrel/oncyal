"""
Icônes de l'application Oncyal : une vague qui s'apaise jusqu'à une branche où est posé un martin-pêcheur.
Écrit dans site/ : apple-touch-icon.png (180), icon-192.png, icon-512.png, icon-maskable-512.png (motif réduit
pour la zone de sécurité des icônes adaptatives Android), et favicon.svg (même dessin, vectoriel).
Lancer :  python icones_06.py
"""
import math, re
from PIL import Image, ImageChops, ImageDraw

FOND, BLEU, BLEU_FONCE, REFLET, ORANGE, BEC, OEIL, JOUE = "#08131d", "#16a0e6", "#0b6fa8", "#7fd3ff", "#f28a2e", "#d9e4ec", "#04121c", "#eaf6fc"
# Oiseau dessiné dans les coordonnées du logo du site (voir index.html), puis placé dans un carré de 100 unités :
# le point (172 ; 18,2) du logo (pattes sur la branche) va en (62 ; 64), à l'échelle 2,6.
Y0 = 58                                              # hauteur de la branche (motif centré)
K, OX, OY = 2.6, 62 - 172 * 2.6, Y0 - 18.2 * 2.6
OISEAU = [
    (BLEU_FONCE, 1, "M161 21.2 L164.6 15.6 L166.8 16.8 Z"),
    (BLEU, 1, "M164 17.2 C164.4 12.4 167.9 9.3 172 9.4 C175.3 9.5 177.3 11.6 177.3 14 C177.3 16.5 175.1 17.6 171.6 17.7 L166 17.7 Z"),
    (REFLET, 0.8, "M167.4 12.6 C169 11.4 171.4 11 173.4 11.6 C171.6 12.2 169.6 13 167.4 12.6 Z"),
    (ORANGE, 1, "M168 17.6 C170.6 18.2 174.6 17.6 176.6 15.2 C177 17.2 174.8 18.8 171.9 18.9 C170.3 18.9 169 18.5 168 17.6 Z"),
    (BEC, 1, "M176.7 12.5 L183.6 13.5 L176.9 14.5 Z"),
]


def vague():
    """Points de la vague (unités du carré de 100) : amplitude décroissante, de gauche à la branche."""
    pts = []
    for i in range(61):
        t = i / 60
        pts.append((8 + 32 * t, Y0 - 9 * math.exp(-2.6 * t) * math.sin(t * 4.5 * math.pi)))
    return pts


def chemin(d):
    """Mini-lecteur de chemin SVG (M, L, C, Z) -> liste de points."""
    tok, pts, cur, i = re.findall(r"[MLCZ]|-?\d*\.?\d+", d), [], (0, 0), 0
    while i < len(tok):
        c = tok[i]
        if c in "ML":
            cur = (float(tok[i + 1]), float(tok[i + 2])); pts.append(cur); i += 3
        elif c == "C":
            p1, p2, p3 = [(float(tok[i + 1 + 2 * k]), float(tok[i + 2 + 2 * k])) for k in range(3)]
            for s in range(1, 21):
                t = s / 20; u = 1 - t
                pts.append((u ** 3 * cur[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                            u ** 3 * cur[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
            cur = p3; i += 7
        else:
            i += 1
    return pts


def dessine(taille, echelle=1.0):
    S = taille * 4                                   # sur-échantillonnage x4 pour un trait lisse
    im = Image.new("RGBA", (S, S), FOND)
    d = ImageDraw.Draw(im, "RGBA")
    u = S / 100 * echelle
    off = S * (1 - echelle) / 2
    P = lambda x, y: (off + x * u, off + y * u)
    L = lambda x, y: P(OX + K * x, OY + K * y)       # coordonnées du logo -> image
    w = max(1, int(3.4 * u))
    trait = Image.new("RGBA", (S, S), (0, 0, 0, 0)); dt = ImageDraw.Draw(trait)
    dt.line([P(*p) for p in vague()] + [P(90, Y0)], fill=BLEU, width=w, joint="curve")          # vague puis branche, d'un seul trait
    for x in (8, 90):
        r = w / 2; c0 = P(x, Y0 if x == 90 else vague()[0][1]); dt.ellipse([c0[0] - r, c0[1] - r, c0[0] + r, c0[1] + r], fill=BLEU)
    # la vague apparaît depuis la gauche : opacité de 15 % au départ à 100 % aux deux cinquièmes de l'icône
    fondu = Image.linear_gradient("L").rotate(90).resize((S, S)).point(lambda a: int(40 + 215 * min(1, a / 255 * 2.4)))
    trait.putalpha(ImageChops.darker(trait.getchannel("A"), fondu))
    im.alpha_composite(trait)
    for coul, op, dd in OISEAU:
        c = Image.new("RGBA", (S, S), (0, 0, 0, 0)); ImageDraw.Draw(c).polygon([L(x, y) for x, y in chemin(dd)], fill=coul)
        if op < 1:
            c.putalpha(c.getchannel("A").point(lambda a: int(a * op)))
        im.alpha_composite(c)
    for (x, y, r, coul) in ((174.6, 12.2, 0.9, OEIL), (175.7, 14.9, 0.8, JOUE)):
        cx, cy = L(x, y); rr = r * K * u; d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=coul)
    for x in (170.2, 172.4):
        d.line([L(x, 18.4), L(x, 19.7)], fill=ORANGE, width=max(1, int(0.8 * K * u)))
    return im.resize((taille, taille), Image.LANCZOS).convert("RGB")


def favicon_svg():
    v = " ".join(f"{x:.1f},{y:.1f}" for x, y in vague())
    oiseau = "".join(f'<path d="{dd}" fill="{c}"' + (f' opacity="{op}"' if op < 1 else "") + "/>" for c, op, dd in OISEAU)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            f'<rect width="100" height="100" rx="22" fill="{FOND}"/>'
            f'<polyline points="{v}" fill="none" stroke="{BLEU}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M40 {Y0} L90 {Y0}" stroke="{BLEU}" stroke-width="4" stroke-linecap="round"/>'
            f'<g transform="translate({OX:.2f} {OY:.2f}) scale({K})">{oiseau}'
            f'<circle cx="174.6" cy="12.2" r=".9" fill="{OEIL}"/><circle cx="175.7" cy="14.9" r=".8" fill="{JOUE}"/></g></svg>')


def image_partage():
    """Image d'aperçu pour les réseaux sociaux (1200 x 630) : motif à gauche, nom et accroche à droite."""
    from PIL import ImageFont
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), FOND)
    motif = dessine(560).crop((0, 90, 560, 470))                    # vague, branche et oiseau, sans le vide autour
    im.paste(motif, (40, (H - motif.height) // 2))
    d = ImageDraw.Draw(im)
    f = lambda nom, t: ImageFont.truetype("C:/Windows/Fonts/" + nom, t)
    x = 640
    d.text((x, 190), "oncyal", font=f("segoeuil.ttf", 112), fill="#e2ebf1")
    d.text((x + 312, 214), "06", font=f("seguisb.ttf", 40), fill=ORANGE)
    d.text((x, 340), "Le chemin le plus calme, à vélo.", font=f("segoeui.ttf", 38), fill="#e2ebf1")
    d.text((x, 398), "Moins de bruit, de pollution", font=f("segoeuil.ttf", 30), fill="#8aa0b0")
    d.text((x, 438), "et de lumière · Alpes-Maritimes", font=f("segoeuil.ttf", 30), fill="#8aa0b0")
    d.rectangle([x, 505, x + 72, 509], fill=BLEU)
    return im


if __name__ == "__main__":
    image_partage().save("site/og.png", optimize=True)
    dessine(180).save("site/apple-touch-icon.png")
    dessine(192).save("site/icon-192.png")
    dessine(512).save("site/icon-512.png")
    dessine(512, echelle=0.76).save("site/icon-maskable-512.png")
    open("site/favicon.svg", "w", encoding="utf-8").write(favicon_svg())
    print("icônes écrites dans site/")
