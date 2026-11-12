import re, requests

BASE = "https://geoservices.atmosud.org/geoserver/mod_sudpaca_2024/"

def get(path, **p):
    return requests.get(BASE + path, params=p, timeout=60)

# 1. Couches et formats proposés par le WMS
r = get("wms", service="WMS", version="1.1.1", request="GetCapabilities")
print("WMS :", r.status_code, r.headers.get("content-type"), len(r.content), "octets")
txt = r.text
names = re.findall(r"<Layer[^>]*>\s*<Name>([^<]+)</Name>", txt)
print(len(names), "couches")
for n in names:
    print("  -", n)
if "<GetMap>" in txt:
    bloc = txt.split("<GetMap>")[1].split("</GetMap>")[0]
    print("Formats GetMap :", sorted(set(re.findall(r"<Format>([^<]+)</Format>", bloc))))

# 2. Le service WCS (valeurs brutes) existe-t-il ?
try:
    r2 = get("wcs", service="WCS", version="2.0.1", request="GetCapabilities")
    print("WCS :", r2.status_code, len(r2.content), "octets")
    print(re.findall(r"<wcs:CoverageId>([^<]+)</wcs:CoverageId>", r2.text)[:20])
except Exception as e:
    print("WCS : erreur", e)

# 3. Essai de récupération d'un petit carré (centre de Nice) en GeoTIFF
if names:
    r3 = get("wms", service="WMS", version="1.1.1", request="GetMap",
             layers=names[0], styles="", srs="EPSG:4326",
             bbox="7.25,43.69,7.27,43.71", width=80, height=80,
             format="image/geotiff")
    print("GetMap geotiff :", r3.status_code, r3.headers.get("content-type"), len(r3.content), "octets")
    print(r3.content[:120])