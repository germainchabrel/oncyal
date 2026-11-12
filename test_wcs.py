import re, requests

BASE = "https://geoservices.atmosud.org/geoserver/mod_sudpaca_2024/wcs"
COVS = ["mod_sudpaca_2024__mod_sudpaca_2024_no2_moyan",
        "mod_sudpaca_2024__mod_sudpaca_2024_icair365"]

for cid in COVS:
    r = requests.get(BASE, params=dict(service="WCS", version="2.0.1",
                     request="DescribeCoverage", coverageId=cid), timeout=60)
    print("\n==", cid, r.status_code, len(r.content), "octets")
    open("describe_" + cid.split("_")[-2] + ".xml", "w", encoding="utf-8").write(r.text)
    t = r.text
    for motif in [r'srsName="[^"]+"', r'axisLabels="[^"]+"',
                  r'<gml:lowerCorner>[^<]+', r'<gml:upperCorner>[^<]+',
                  r'<gml:high>[^<]+', r'<gml:offsetVector[^>]*>[^<]+',
                  r'<swe:uom code="[^"]+"', r'<swe:label>[^<]+',
                  r'<swe:NilValue[^>]*>[^<]*']:
        print("  ", motif[:22], "->", re.findall(motif, t)[:3])

# Essai : un petit carré autour du centre de Nice, en vraies valeurs
cid = COVS[0]
r = requests.get(BASE, params=[
    ("service", "WCS"), ("version", "2.0.1"), ("request", "GetCoverage"),
    ("coverageId", cid), ("format", "image/tiff"),
    ("subsettingCrs", "http://www.opengis.net/def/crs/EPSG/0/4326"),
    ("subset", "Lat(43.69,43.71)"), ("subset", "Long(7.25,7.27)")], timeout=120)
print("\nGetCoverage :", r.status_code, r.headers.get("content-type"), len(r.content), "octets")
if r.content[:2] in (b"II", b"MM"):
    open("essai_no2.tif", "wb").write(r.content)
    try:
        import tifffile
        with tifffile.TiffFile("essai_no2.tif") as tf:
            a = tf.asarray()
            print("forme", a.shape, "type", a.dtype, "min", a.min(), "max", a.max())
            for k in ("ModelPixelScaleTag", "ModelTiepointTag", "GeoAsciiParamsTag"):
                t = tf.pages[0].tags.get(k)
                print(k, t.value if t else None)
    except ImportError:
        print("installe d'abord :  pip install tifffile")
else:
    print(r.text[:800])