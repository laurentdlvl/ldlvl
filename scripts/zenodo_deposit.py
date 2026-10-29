#!/usr/bin/env python3
"""Deposit each published resource on Zenodo, one record (and one DOI) per resource.

For every sources/<slug>.h5p whose sidecar version has not yet been deposited on the
chosen target, the script:
  - creates a Zenodo record (first deposit) or a new version of it (later deposits),
    so that all versions share one concept DOI;
  - uploads the .h5p package and the metadata;
  - publishes, then writes the identifiers back into sources/<slug>.json under
    "zenodo" -> "<target>".

Only on the production target are the DOIs also copied to the top-level "doi" and
"conceptDoi" fields, which the site displays. Sandbox DOIs are test values and
never reach the public pages.

Resources are skipped when they lack a Creative Commons licence or an author, and,
on production only, while their description is still marked [draft].

Standard library only. Environment: ZENODO_TOKEN.
Usage:
  python3 scripts/zenodo_deposit.py --target sandbox|production [--only <slug>] [--dry-run]
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402  (reuses licence and metadata helpers)

ROOT = build.ROOT
TARGETS = {"sandbox": "https://sandbox.zenodo.org/api", "production": "https://zenodo.org/api"}
LANG3 = {"en": "eng", "fr": "fra", "de": "deu", "es": "spa", "it": "ita", "pt": "por", "hr": "hrv", "sl": "slv"}
API = os.environ.get("ZENODO_API")  # set by tests to point at a local mock


def notice(msg):
    print(f"::notice::{msg}" if os.environ.get("GITHUB_ACTIONS") else msg, flush=True)


class Zenodo:
    def __init__(self, base, token, dry):
        self.base, self.token, self.dry = base.rstrip("/"), token, dry

    def call(self, method, url, data=None, raw=None, ctype="application/json"):
        if not url.startswith("http"):
            url = self.base + url
        if self.dry:
            print(f"  [dry-run] {method} {url}")
            return {"id": 0, "links": {"bucket": "bucket", "latest_draft": f"{self.base}/deposit/depositions/0"},
                    "doi": "10.0000/dry", "conceptdoi": "10.0000/dry-concept", "conceptrecid": "0", "files": []}
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                txt = r.read().decode() or "{}"
                return json.loads(txt) if txt.strip().startswith(("{", "[")) else {}
        except urllib.error.HTTPError as err:
            raise SystemExit(f"Zenodo {method} {url} failed: {err.code} {err.read().decode()[:500]}")


def metadata(slug, h5p, side, lic, cfg, base):
    rec = build.amb_record(slug, h5p, side, lic, cfg, base)
    page = rec["id"]
    desc = build.clean(side.get("description", ""))
    langs = rec.get("inLanguage", ["en"])
    md = {
        "upload_type": "lesson",
        "title": side.get("title") or h5p.get("title"),
        "description": (f"<p>{build.e(desc)}</p>"
                        f"<p>Interactive H5P package. Play it online: <a href=\"{page}\">{page}</a>. "
                        "Import the .h5p file into Moodle (H5P activity or content bank) or any platform that supports H5P.</p>"),
        "creators": [{"name": c["name"], **({"orcid": c["id"].rsplit("/", 1)[-1]} if "orcid.org" in c.get("id", "") else {})}
                     for c in rec.get("creator", [])],
        "access_right": "open",
        "license": "cc-" + lic[0][3:].lower() + "-" + lic[1],
        "keywords": side.get("keywords", []),
        "language": LANG3.get(langs[0], langs[0]),
        "version": side.get("version", ""),
        "publication_date": side.get("datePublished") or dt.date.today().isoformat(),
        "related_identifiers": [{"identifier": page, "relation": "isDescribedBy", "resource_type": "lesson"}],
        "publisher": cfg["publisher"]["name"],
    }
    if side.get("isPartOf"):
        md["related_identifiers"].append({"identifier": side["isPartOf"], "relation": "isPartOf"})
    if cfg.get("repositoryUrl"):
        md["related_identifiers"].append({"identifier": cfg["repositoryUrl"], "relation": "isSupplementTo"})
    if cfg.get("zenodo", {}).get("communities"):
        md["communities"] = [{"identifier": c} for c in cfg["zenodo"]["communities"]]
    return md


def deposit(z, pkg, side, md, prev):
    if prev and prev.get("recordId"):
        r = z.call("POST", f"/deposit/depositions/{prev['recordId']}/actions/newversion")
        draft = z.call("GET", r["links"]["latest_draft"])
        for f in draft.get("files", []):
            z.call("DELETE", f["links"]["self"])
    else:
        draft = z.call("POST", "/deposit/depositions", data={})
    did = draft["id"]
    with open(pkg, "rb") as fh:
        z.call("PUT", f"{draft['links']['bucket']}/{pkg.name}", raw=fh.read(), ctype="application/octet-stream")
    z.call("PUT", f"/deposit/depositions/{did}", data={"metadata": md})
    pub = z.call("POST", f"/deposit/depositions/{did}/actions/publish")
    return {"recordId": pub.get("id", did), "conceptRecid": str(pub.get("conceptrecid", "")),
            "doi": pub.get("doi", ""), "conceptDoi": pub.get("conceptdoi", ""),
            "version": side.get("version", ""), "date": dt.date.today().isoformat()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=TARGETS, default="sandbox")
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    token = os.environ.get("ZENODO_TOKEN", "")
    if not token and not a.dry_run:
        raise SystemExit("ZENODO_TOKEN is not set. Add it as a repository secret.")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    base = cfg["baseUrl"].rstrip("/") + "/"
    z = Zenodo(API or TARGETS[a.target], token, a.dry_run)
    done = 0
    for pkg in sorted((ROOT / "sources").glob("*.h5p")):
        slug = pkg.stem
        if a.only and slug != a.only:
            continue
        side_path = pkg.with_suffix(".json")
        side = json.loads(side_path.read_text(encoding="utf-8")) if side_path.exists() else {}
        with zipfile.ZipFile(pkg) as zf:
            h5p = json.loads(zf.read("h5p.json"))
        lic = build.licence_info(h5p, side)
        creators = side.get("creators") or [x for x in h5p.get("authors", []) if x.get("name")]
        prev = side.get("zenodo", {}).get(a.target, {})
        reasons = []
        if not lic:
            reasons.append("no Creative Commons licence")
        if not creators:
            reasons.append("no author")
        if a.target == "production" and str(side.get("description", "")).startswith("[draft]"):
            reasons.append("description still marked [draft]")
        if reasons:
            notice(f"{slug}: skipped ({', '.join(reasons)})")
            continue
        if prev.get("version") == side.get("version"):
            notice(f"{slug}: version {side.get('version')} already on {a.target} ({prev.get('doi')})")
            continue
        md = metadata(slug, h5p, side, lic, cfg, base)
        print(f"{slug}: depositing version {side.get('version')} on {a.target}")
        out = deposit(z, pkg, side, md, prev)
        if a.dry_run:
            print(json.dumps(md, indent=2, ensure_ascii=False))
            continue
        side.setdefault("zenodo", {})[a.target] = out
        if a.target == "production":
            side["doi"], side["conceptDoi"] = out["doi"], out["conceptDoi"]
        side_path.write_text(json.dumps(side, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        notice(f"{slug}: published on {a.target}, DOI {out['doi']} (concept {out['conceptDoi']})")
        done += 1
    print(f"{done} resource(s) deposited on {a.target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
