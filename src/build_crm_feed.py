"""Daily CRM catalog feed for CleverTap (Catalog Send-Time Personalization).

Joins config/crm_city_map.csv (identity -> slug: the distinct CleverTap `City` values mapped to our
209 slugs, frozen so this step needs no gazetteer resolver) with today's data/grid.json (top disease /
band / score, which change daily) + config/site.json (URLs), and writes the upload-ready catalog CSV in
the exact CleverTap schema (identity, Name, ImageURL mandatory; plus deep_link, prod variants, and the
dynamic top_disease / band / score).

Run in .github/workflows/daily.yml AFTER build_site so the file lands in the deployed site under crm/,
where the CRM team downloads it directly or a Google Sheet =IMPORTDATA() auto-pulls it. Refreshing the
CleverTap city set = re-export from CleverTap and update config/crm_city_map.csv (occasional).

  python src/build_crm_feed.py [output_csv_path]
Default output: dist/fever-watch/crm/FeverWatch_Cities_catalog.csv
"""
import csv, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "config", "crm_city_map.csv")
GRID = os.path.join(ROOT, "data", "grid.json")
SITE = os.path.join(ROOT, "config", "site.json")
DEFAULT_OUT = os.path.join(ROOT, "dist", "fever-watch", "crm", "FeverWatch_Cities_catalog.csv")

# grid band -> title-case for the copy; keep byte-consistent with build_crm_feed's only casing source.
BANDFMT = {"HIGH": "High", "MODERATE": "Moderate", "LOW": "Low", "LOW-MODERATE": "Low-moderate"}
# CleverTap catalog schema: identity (key), Name + ImageURL (mandatory), then our attributes. <= 20 cols.
COLS = ["identity", "Name", "ImageURL", "deep_link", "ImageURL_prod", "deep_link_prod",
        "top_disease", "band", "score", "matched_slug"]


def build(out_path: str) -> int:
    site = json.load(open(SITE, encoding="utf-8"))
    base, stg = site["base_url"], site["staging_url"]
    g = json.load(open(GRID, encoding="utf-8"))
    dis = {d["id"]: d["label"] for d in g["diseases"]}
    blend = {c["id"]: c["blend"] for c in g["cities"]}
    name = {c["id"]: c["name"] for c in g["cities"]}

    rows, missing = [], []
    with open(MAP, encoding="utf-8") as fh:
        for m in csv.DictReader(fh):
            ident, slug = m["identity"].strip(), m["slug"].strip()
            if slug not in blend:                      # stale map row (city dropped from the 209)
                missing.append(ident)
                continue
            b = blend[slug]
            rows.append({
                "identity": ident, "Name": name[slug],
                "ImageURL": stg + "assets/img/push/" + slug + ".jpg",   # active (staging origin, live today)
                "deep_link": stg + slug + "/",
                "ImageURL_prod": base + "assets/img/push/" + slug + ".jpg",  # parked until the prod route is live
                "deep_link_prod": base + slug + "/",
                "top_disease": dis.get(b["driver"], b["driver"]),
                "band": BANDFMT.get(b["band"], b["band"].title()),
                "score": b["score"], "matched_slug": slug,
            })

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:   # plain UTF-8, no BOM (CleverTap-safe)
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print("CRM feed: %d rows -> %s (grid generated_at %s)" % (len(rows), out_path, g.get("generated_at", "")))
    if missing:
        print("WARNING: %d map rows point at slugs not in grid.json (skipped): %s" % (len(missing), missing))
    return len(rows)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
