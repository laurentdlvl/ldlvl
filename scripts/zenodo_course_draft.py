#!/usr/bin/env python3
"""Create a Zenodo DRAFT for a course archive and reserve its DOI. Never publishes.

Course archives (Moodle backup + extracted learning resources) are too large for this
repository, so files are uploaded by hand in the Zenodo web form. This script only:
  - checks courses/<slug>/zenodo-metadata.json (no {{TO_COMPLETE}} left, unless allowed);
  - creates a draft deposition on the chosen target with that metadata;
  - reserves its DOI;
  - writes the record id, DOI and edit link to courses/<slug>/zenodo-draft.json.

It refuses to create a second draft for the same course and target while one is recorded
(use --force to replace the record of it, e.g. after deleting the draft on Zenodo).

Standard library only. Environment: ZENODO_TOKEN.
Usage:
  python3 scripts/zenodo_course_draft.py --course xml-publishing --target sandbox [--allow-placeholders] [--dry-run]
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {"sandbox": "https://sandbox.zenodo.org", "production": "https://zenodo.org"}
PRIVATE_KEYS = ("_note", "files_expected")


def notice(msg):
    print(f"::notice::{msg}" if os.environ.get("GITHUB_ACTIONS") else msg, flush=True)


def call(method, url, token, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode() or "{}"
            return json.loads(txt)
    except urllib.error.HTTPError as err:
        raise SystemExit(f"Zenodo {method} {url} failed: {err.code} {err.read().decode()[:1500]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--course", required=True, help="folder name under courses/")
    ap.add_argument("--target", choices=TARGETS, default="sandbox")
    ap.add_argument("--allow-placeholders", action="store_true", help="sandbox tests only")
    ap.add_argument("--force", action="store_true", help="create a new draft even if one is recorded")
    ap.add_argument("--dry-run", action="store_true", help="print what would be sent, send nothing")
    a = ap.parse_args()

    folder = ROOT / "courses" / a.course
    meta_path, out_path = folder / "zenodo-metadata.json", folder / "zenodo-draft.json"
    raw = meta_path.read_text(encoding="utf-8")
    meta = json.loads(raw)

    if "{{TO_COMPLETE" in raw:
        if a.target == "production" or not a.allow_placeholders:
            raise SystemExit(f"{meta_path.relative_to(ROOT)} still contains {{{{TO_COMPLETE}}}} placeholders. "
                             "Fill them (allowed on sandbox with --allow-placeholders).")
        notice("Placeholders left in the metadata: accepted for this sandbox test only.")

    record = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if record.get(a.target) and not a.force:
        prev = record[a.target]
        notice(f"A draft is already recorded on {a.target}: record {prev['record_id']}, DOI {prev['doi']}, {prev['edit_url']}")
        return 0

    md = {k: v for k, v in meta.items() if k not in PRIVATE_KEYS}
    md["prereserve_doi"] = True
    base = os.environ.get("ZENODO_BASE") or TARGETS[a.target]  # ZENODO_BASE: local mock for tests
    if a.dry_run:
        print(json.dumps({"metadata": md}, indent=2, ensure_ascii=False))
        return 0

    token = os.environ.get("ZENODO_TOKEN", "")
    if not token:
        raise SystemExit("ZENODO_TOKEN is not set. Add it as a repository secret.")

    dep = call("POST", f"{base}/api/deposit/depositions", token, {"metadata": md})
    rid = dep["id"]
    doi = (dep.get("metadata", {}).get("prereserve_doi") or {}).get("doi")
    if not doi:  # fall back on the InvenioRDM endpoint
        res = call("POST", f"{base}/api/records/{rid}/draft/pids/doi", token)
        doi = res.get("pids", {}).get("doi", {}).get("identifier")
    if not doi:
        raise SystemExit(f"Draft {rid} created, but no DOI was reserved. Reserve it in the web form.")

    record[a.target] = {
        "record_id": rid, "doi": doi, "edit_url": f"{base}/uploads/{rid}",
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "files_to_upload": meta.get("files_expected", []), "published": False}
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notice(f"{a.course}: draft {rid} created on {a.target}, DOI reserved {doi}. "
           f"Upload the files and publish at {base}/uploads/{rid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
