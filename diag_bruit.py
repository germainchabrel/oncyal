"""
Diagnostic du bruit : lit out/reseau_06.csv.gz (ne modifie rien).
Lancer depuis le dossier du projet :  python diag_bruit.py
"""
import pandas as pd
from prepare_06 import HW

e = pd.read_csv("out/reseau_06.csv.gz")
e["type"] = [HW[i] for i in e.hw.values]
e["officiel"] = e.noise_src == 1

print("\n=== GRANDES VOIES : part de bouts de rue 'officiels' et niveau de bruit ===")
for t in ["motorway", "motorway_link", "trunk", "trunk_link", "primary"]:
    s = e[e.type == t]
    if s.empty:
        continue
    off, est = s[s.officiel], s[~s.officiel]
    print(f"\n{t} : {len(s)} bouts de rue, {100 * len(off) / len(s):.0f} % officiels")
    if len(off):
        print("   officiels : bruit moyen", round(off.noise.mean(), 1), "dB | 10e centile", round(off.noise.quantile(.1), 1), "| 90e centile", round(off.noise.quantile(.9), 1))
        print("   officiels sous 65 dB :", f"{100 * (off.noise < 65).mean():.0f} %")
    if len(est):
        print("   estimés   : bruit moyen", round(est.noise.mean(), 1), "dB")

print("\n=== AUTOROUTES OFFICIELLES : répartition du bruit (dB) ===")
m = e[(e.type == "motorway") & e.officiel]
if len(m):
    print(pd.cut(m.noise, [0, 57.5, 62.5, 67.5, 72.5, 200], right=False).value_counts().sort_index().to_string())

print("\n=== ZONE DE L'AÉROPORT DE NICE (cadre approximatif) ===")
a = e[(e.alon.between(7.20, 7.24)) & (e.alat.between(43.645, 43.67))]
print(len(a), "bouts de rue dans le cadre")
g = a.groupby("type").agg(n=("noise", "size"), part_officiel=("officiel", "mean"), bruit_moyen=("noise", "mean")).round(2)
print(g.sort_values("n", ascending=False).to_string())
