#!/usr/bin/env python3
"""Build a static site from H5P packages.

For each sources/<slug>.h5p (plus an optional sources/<slug>.json sidecar), the build:
  - extracts the package for the h5p-standalone player   -> _site/content/<slug>/
  - copies the package for download                       -> _site/downloads/<slug>.h5p
  - writes a page with the player, licence, Dublin Core,
    citation tags and AMB-compatible JSON-LD              -> _site/r/<slug>/index.html
  - writes the record on its own                          -> _site/r/<slug>/metadata.json
  - checks the resource against the minimum set (socle)   -> shown on the page and in the log
Then it writes the catalogue (index.html), a metadata dump (catalog.json),
sitemap.xml and robots.txt. Only resources with a declared Creative Commons
licence are exposed for harvesting.

Standard library only. Usage:
  python3 scripts/build.py [--base-url https://owner.github.io/repo/] [--out _site]
"""
import argparse
import datetime as dt
import html
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview import page_preview  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

LICENCES = {
    "CC BY": ("by", "Creative Commons Attribution"),
    "CC BY-SA": ("by-sa", "Creative Commons Attribution-ShareAlike"),
    "CC BY-NC": ("by-nc", "Creative Commons Attribution-NonCommercial"),
    "CC BY-NC-SA": ("by-nc-sa", "Creative Commons Attribution-NonCommercial-ShareAlike"),
    "CC BY-ND": ("by-nd", "Creative Commons Attribution-NoDerivatives"),
    "CC BY-NC-ND": ("by-nc-nd", "Creative Commons Attribution-NonCommercial-NoDerivatives"),
}
LANGS = {"en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese", "hr": "Croatian", "sl": "Slovenian"}
lang_names = lambda codes: ", ".join(LANGS.get(c, c) for c in codes)

H5P_TYPES = {
    "H5P.InteractiveBook": "Interactive book",
    "H5P.CoursePresentation": "Course presentation",
    "H5P.InteractiveVideo": "Interactive video",
    "H5P.QuestionSet": "Quiz",
}

e = lambda s: html.escape(str(s), quote=True)


def safe_extract(zip_path, dest):
    """Extract a zip while refusing entries that would land outside dest."""
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            target = (dest / m.filename).resolve()
            if dest not in target.parents and target != dest:
                raise ValueError(f"{zip_path.name}: unsafe path {m.filename!r}")
        z.extractall(dest)


def licence_info(h5p, side):
    """Return (code, version, uri, label) or None when no CC licence is declared."""
    raw = (side.get("licence") or "").strip()
    if raw:
        parts = raw.rsplit(" ", 1)
        code, ver = (parts[0], parts[1]) if len(parts) == 2 and parts[1][0].isdigit() else (raw, "4.0")
    else:
        code, ver = h5p.get("license", "U"), h5p.get("licenseVersion", "4.0")
    if code not in LICENCES:
        return None
    slug, name = LICENCES[code]
    return code, ver, f"https://creativecommons.org/licenses/{slug}/{ver}/", f"{name} {ver}"


def clean(text):
    return text[len("[draft]"):].strip() if text.startswith("[draft]") else text


def socle(h5p, side, lic):
    """Check the minimum set: OER definition plus FAIR-by-Design minimum elements."""
    desc_missing = [label for k, label in (
        ("description", "description"), ("audience", "audience"),
        ("learningObjectives", "learning objectives"), ("prerequisites", "prerequisites"),
        ("timeRequired", "time required")) if not side.get(k)]
    draft = str(side.get("description", "")).startswith("[draft]")
    creators = side.get("creators") or [a for a in h5p.get("authors", []) if a.get("name")]
    rows = [
        ("Creative Commons licence, clearly stated",
         "ok" if lic else "missing",
         lic[3] if lic else "The package declares no licence. Set it in the authoring tool or in the sidecar file."),
        ("Free access", "ok", "Open on this site, no account needed."),
        ("Persistent identifier", "ok" if side.get("doi") else "missing",
         f"DOI {side['doi']}" if side.get("doi") else "Deposit this resource on Zenodo and record its DOI in the sidecar file."),
        ("Metadata following a recognised schema", "ok" if lic else "missing",
         "AMB-compatible JSON-LD and Dublin Core generated on this page." if lic else "Not exposed until the licence is declared."),
        ("Complete description", "missing" if desc_missing else ("check" if draft else "ok"),
         ("Missing: " + ", ".join(desc_missing) + "." if desc_missing else "") + (" Description drafted, to be validated by the author." if draft else "")),
        ("Access conditions stated, accessibility checked",
         "ok" if side.get("accessibility") else "missing",
         "Access: open, no login. " + (side.get("accessibility") or "Accessibility not yet checked.")),
        ("Editable source in an open format", "ok", "The .h5p package is the editable source (open H5P format)."),
        ("Third-party content credited",
         {True: "ok", False: "missing", None: "check"}[side.get("thirdPartyContentCredited")],
         "To check by the author." if side.get("thirdPartyContentCredited") is None else ""),
    ]
    if not creators:
        rows[0] = (rows[0][0], rows[0][1], rows[0][2] + " No author declared.")
    return rows


def amb_record(slug, h5p, side, lic, cfg, base):
    page = f"{base}r/{slug}/"
    rec = {
        "@context": ["https://w3id.org/kim/amb/context.jsonld", {"@language": cfg.get("language", "en")}],
        "id": page,
        "type": ["LearningResource"],
        "name": side.get("title") or h5p.get("title"),
        "description": clean(side.get("description", "")),
        "inLanguage": side.get("inLanguage") or [h5p.get("defaultLanguage", "en")],
        "isAccessibleForFree": True,
        "conditionsOfAccess": {"id": "http://w3id.org/kim/conditionsOfAccess/no_login", "type": "Concept"},
        "learningResourceType": [{"id": "https://w3id.org/kim/hcrt/course", "type": "Concept", "prefLabel": {"en": "Course"}}],
        "interactivityType": {"id": f"http://purl.org/dcx/lrmi-vocabs/interactivityType/{side.get('interactivityType', 'mixed')}", "type": "Concept"},
        "keywords": side.get("keywords", []) + [n for n in side.get("_themes", []) if n not in side.get("keywords", [])],
        "creator": [{"type": c.get("type", "Organization"), "name": c["name"], **({"id": c["id"]} if c.get("id") else {})}
                    for c in (side.get("creators") or [{"name": a["name"]} for a in h5p.get("authors", []) if a.get("name")])],
        "publisher": [{"type": "Organization", "name": cfg["publisher"]["name"], "id": cfg["publisher"]["url"]}],
        "mainEntityOfPage": [{"id": page, "provider": {"id": base, "type": "Service", "name": cfg["siteTitle"]}}],
        "encoding": [{"type": "MediaObject", "contentUrl": f"{base}downloads/{slug}.h5p", "encodingFormat": "application/zip"}],
        "version": side.get("version", ""),
    }
    if lic:
        rec["license"] = {"id": lic[2]}
    # AMB requires audience ids from the LRMI educationalAudienceRole vocabulary;
    # the free-text audience in the sidecar is shown on the page only.
    if side.get("audienceRole"):
        rec["audience"] = [{"id": f"http://purl.org/dcx/lrmi-vocabs/educationalAudienceRole/{r}", "type": "Concept",
                            "prefLabel": {"en": r}} for r in side["audienceRole"]]
    if side.get("timeRequired"):
        rec["timeRequired"] = side["timeRequired"]
    if side.get("datePublished"):
        rec["datePublished"] = side["datePublished"]
    if side.get("doi"):
        rec["sameAs"] = [f"https://doi.org/{side['doi']}"]
    if side.get("isPartOf"):
        rec["isPartOf"] = [{"id": side["isPartOf"], "type": ["LearningResource", "Course"]}]
    return {k: v for k, v in rec.items() if v not in ("", [], None)}


def head(title, desc, extra=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{extra}<link rel="stylesheet" href="{{root}}assets/site.css">
</head>
<body>
"""


def page_resource(slug, h5p, side, lic, rows, rec, cfg, exposed):
    root = "../../"
    title = side.get("title") or h5p.get("title")
    desc = clean(side.get("description", ""))
    creators = ", ".join(c["name"] for c in rec.get("creator", [])) or "Author not declared"
    meta = [f'<meta name="robots" content="{"index,follow" if exposed else "noindex"}">',
            f'<link rel="canonical" href="{e(rec["id"])}">',
            f'<meta name="DC.title" content="{e(title)}">',
            f'<meta name="DC.description" content="{e(desc)}">',
            f'<meta name="DC.type" content="InteractiveResource">',
            f'<meta name="DC.format" content="application/zip">',
            f'<meta name="DC.publisher" content="{e(cfg["publisher"]["name"])}">',
            f'<meta name="DC.identifier" content="{e(rec["id"])}">']
    meta += [f'<meta name="DC.language" content="{e(l)}">' for l in rec.get("inLanguage", [])]
    meta += [f'<meta name="DC.creator" content="{e(c["name"])}">' for c in rec.get("creator", [])]
    meta += [f'<meta name="DC.subject" content="{e(k)}">' for k in rec.get("keywords", [])]
    meta += [f'<meta name="citation_title" content="{e(title)}">']
    meta += [f'<meta name="citation_author" content="{e(c["name"])}">' for c in rec.get("creator", [])]
    if side.get("datePublished"):
        meta += [f'<meta name="DC.date" content="{e(side["datePublished"])}">', f'<meta name="citation_publication_date" content="{e(side["datePublished"])}">']
    if side.get("doi"):
        meta += [f'<meta name="citation_doi" content="{e(side["doi"])}">']
    if lic:
        meta += [f'<meta name="DC.rights" content="{e(lic[2])}">', f'<link rel="license" href="{e(lic[2])}">']
    if exposed:
        meta += ['<script type="application/ld+json">' + json.dumps(rec, ensure_ascii=False).replace("</", "<\\/") + "</script>"]
    out = head(f"{title} | {cfg['siteTitle']}", desc, "\n".join(meta) + "\n").replace("{root}", root)
    kind = H5P_TYPES.get(h5p.get("mainLibrary"), "Interactive content")
    labels = {"ok": "Met", "check": "To check", "missing": "Missing"}
    met = sum(r[1] == "ok" for r in rows)
    theme_links = ", ".join(f'<a href="{root}themes/{th["slug"]}/">{e(th["name"])}</a>' for th in side.get("_themeRefs", []))
    theme_html = f"<div><dt>Theme</dt><dd>{theme_links}</dd></div>" if theme_links else ""
    lic_block = (f'<a href="{e(lic[2])}" rel="license">{e(lic[3])}</a>' if lic else
                 '<strong class="warn">No licence declared.</strong> Reuse is not permitted until the author declares one.')
    out += f"""<header class="site"><a class="home" href="{root}">{e(cfg['siteTitle'])}</a></header>
<main class="resource">
  <p class="kind">{e(kind)}, in {e(lang_names(rec.get("inLanguage", [])))}</p>
  <h1>{e(title)}</h1>
  <p class="lede">{e(desc)}</p>
  {'' if exposed else '<p class="banner">This resource is visible here but not exposed to catalogues and search engines: its licence is not declared.</p>'}
  <div id="h5p-container" class="player" aria-label="Interactive content: {e(title)}"></div>
  <noscript><p class="banner">The interactive player needs JavaScript. You can still download the package below.</p></noscript>
  <section class="reuse" aria-labelledby="reuse-h">
    <h2 id="reuse-h">Reuse this resource</h2>
    <p class="actions">{f'<a class="btn primary" href="{root}downloads/{slug}.h5p" download>Download the .h5p package</a>' if lic else ''}
    <a class="btn" href="metadata.json">Metadata (JSON-LD)</a></p>
    <dl class="facts">
      <div><dt>Licence</dt><dd>{lic_block}</dd></div>
      {theme_html}
      <div><dt>Author</dt><dd>{e(creators)}</dd></div>
      <div><dt>Publisher</dt><dd><a href="{e(cfg['publisher']['url'])}">{e(cfg['publisher']['name'])}</a></dd></div>
      <div><dt>Version</dt><dd>{e(side.get('version') or 'not set')}</dd></div>
      <div><dt>Persistent identifier</dt><dd>{f'<a href="https://doi.org/{e(side["doi"])}">doi:{e(side["doi"])}</a> (version {e(side.get("version", ""))})' if side.get('doi') else 'not yet assigned'}{f'<br>All versions: <a href="https://doi.org/{e(side["conceptDoi"])}">doi:{e(side["conceptDoi"])}</a>' if side.get('conceptDoi') else ''}</dd></div>
      {f"<div><dt>Audience</dt><dd>{e(', '.join(side['audience']))}</dd></div>" if side.get('audience') else ''}
    </dl>
    <details>
      <summary>How to reuse it in a learning platform</summary>
      <ul>
        <li><strong>Moodle 4.x:</strong> add an <em>H5P</em> activity and upload the package, or import it into the content bank. Moodle installs the H5P libraries it contains.</li>
        <li><strong>Other platforms:</strong> any platform with H5P support (WordPress, Drupal, ILIAS) can import the package.</li>
        <li><strong>Edit offline:</strong> open the package in an H5P editor such as Lumi, adapt it, and keep the attribution.</li>
        <li><strong>Attribution:</strong> {f"credit {e(creators)}, link to this page and state the licence." if rec.get("creator") else "the author and licence must be declared before this resource can be reused."}</li>
      </ul>
    </details>
    <details>
      <summary>Minimum requirements: {met} of {len(rows)} met</summary>
      <table class="socle">
        <thead><tr><th scope="col">Requirement</th><th scope="col">Status</th><th scope="col">Detail</th></tr></thead>
        <tbody>{''.join(f'<tr><td>{e(r[0])}</td><td><span class="st {r[1]}">{labels[r[1]]}</span></td><td>{e(r[2])}</td></tr>' for r in rows)}</tbody>
      </table>
      <p class="note"><a href="{root}preview/{slug}/">Import preview</a>: where each field of this page would come from once resources are imported from Moodle.</p>
      <p class="note">Based on the definition of open educational resources (UNESCO, 2019) and the FAIR-by-Design minimum elements (Skills4EOSC). Results are not tracked on this site; to follow learners' progress, use the package in a learning platform.</p>
    </details>
  </section>
</main>
<script src="{root}vendor/h5p-standalone/main.bundle.js"></script>
<script>
  new H5PStandalone.H5P(document.getElementById('h5p-container'), {{
    h5pJsonPath: '{root}content/{slug}',
    frameJs: '{root}vendor/h5p-standalone/frame.bundle.js',
    frameCss: '{root}vendor/h5p-standalone/styles/h5p.css',
    frame: true, copyright: true, icon: true, fullScreen: true,
    export: {'true' if lic else 'false'}, downloadUrl: '{root}downloads/{slug}.h5p'
  }});
</script>
</body>
</html>
"""
    return out


FACETS = [("format", "Format"), ("language", "Language"), ("audience", "Audience"), ("licence", "Licence"), ("duration", "Time required")]


def themes_of(side, cfg):
    """Map the sidecar's Moodle category name(s) to theme slugs from config.json."""
    raw = side.get("moodleCategory") or []
    names = [raw] if isinstance(raw, str) else raw
    by_name = {t["name"].casefold(): t["slug"] for t in cfg.get("themes", [])}
    found, unknown = [], []
    for n in names:
        (found if n.casefold() in by_name else unknown).append(by_name.get(n.casefold(), n))
    return found, unknown


def page_index(items, cfg, root="./", theme=None):
    themes = cfg.get("themes", [])
    tname = {t["slug"]: t["name"] for t in themes}
    shown = [it for it in items if theme is None or theme in it["themes"]]
    title = cfg["siteTitle"] if theme is None else f"{tname[theme]} | {cfg['siteTitle']}"
    desc = cfg["siteDescription"] if theme is None else f"Open H5P learning resources on {tname[theme]}."
    out = head(title, desc).replace("{root}", root)

    tabs = [f'<li><a class="tab" href="{root}" data-tab="" {"aria-current=page" if theme is None else ""}>All <span class="n">{len(items)}</span></a></li>']
    for t in themes:
        n = sum(t["slug"] in it["themes"] for it in items)
        cur = "aria-current=page" if theme == t["slug"] else ""
        tabs.append(f'<li><a class="tab{" empty" if n == 0 else ""}" href="{root}themes/{t["slug"]}/" data-tab="{t["slug"]}" {cur}>{e(t["name"])} <span class="n">{n}</span></a></li>')

    facet_html = []
    for key, label in FACETS:
        values = {}
        for it in shown:
            for v in it["facets"].get(key, []):
                values[v] = values.get(v, 0) + 1
        if len(values) < 2:
            continue
        opts = "".join(
            f'<li><label><input type="checkbox" name="{key}" value="{e(v)}"> <span class="lbl">{e(v)}</span> <span class="n" data-count>{c}</span></label></li>'
            for v, c in sorted(values.items(), key=lambda kv: (-kv[1], kv[0])))
        facet_html.append(f'<fieldset class="facet" data-facet="{key}"><legend>{e(label)}</legend><ul>{opts}</ul></fieldset>')

    cards, data = [], []
    for it in shown:
        lic = it["lic"]
        met = sum(r[1] == "ok" for r in it["rows"])
        chips = "".join(f'<a class="chip" href="{root}themes/{s}/">{e(tname[s])}</a>' for s in it["themes"])
        cards.append(f"""<li class="card" data-slug="{it['slug']}">
      {f'<p class="chips">{chips}</p>' if chips else ''}
      <h2><a href="{root}r/{it['slug']}/">{e(it['title'])}</a></h2>
      <p>{e(it['desc'])}</p>
      <dl class="meta">
        <div><dt>Format</dt><dd>{e(it['kind'])}, in {e(lang_names(it['lang']))}</dd></div>
        <div><dt>Licence</dt><dd>{e(lic[3]) if lic else '<span class="warn">Not declared</span>'}</dd></div>
        <div><dt>Minimum requirements</dt><dd>{met} of {len(it['rows'])} met{'' if it['exposed'] else ', not exposed to catalogues'}</dd></div>
      </dl>
      <p class="actions"><a class="btn primary" href="{root}r/{it['slug']}/">Open</a> {f'<a class="btn" href="{root}downloads/{it["slug"]}.h5p" download>Download</a>' if lic else ''}</p>
    </li>""")
        data.append({"slug": it["slug"], "text": it["search"], "facets": it["facets"]})

    heading = cfg["siteTitle"] if theme is None else tname[theme]
    lede = (f"{e(cfg['siteDescription'])} Each resource can be played here, downloaded as an .h5p package, and imported into Moodle or any platform that supports H5P."
            if theme is None else f"Resources from the EDCH Training courses in the {e(tname[theme])} category.")
    empty_theme = '<p class="empty-state">No resource in this theme yet.</p>' if not shown else ""
    out += f"""<header class="site"><a class="home" href="{root}">{e(cfg['siteTitle'])}</a></header>
<main class="catalogue">
  <h1>{e(heading)}</h1>
  <p class="lede">{lede}</p>
  <nav class="tabs" aria-label="Themes"><ul>{''.join(tabs)}</ul></nav>
  {empty_theme}
  <div class="browse"{' hidden' if not shown else ''}>
    <aside class="filters" aria-label="Filters">
      <label class="search-label" for="q">Search</label>
      <input id="q" type="search" placeholder="Title, topic, keyword" autocomplete="off">
      {f'<details class="facets" id="facets" open><summary>Filters</summary>' + ''.join(facet_html) + '</details>' if facet_html else ''}
      <button type="button" class="link-btn" id="clear" hidden>Clear filters</button>
    </aside>
    <section aria-label="Results">
      <p class="count" id="count" aria-live="polite">{len(shown)} resource{'s' if len(shown) != 1 else ''}</p>
      <ul class="cards">
        {''.join(cards)}
      </ul>
      <p class="empty-state" id="none" hidden>No resource matches these filters. <button type="button" class="link-btn" id="clear2">Clear filters</button></p>
    </section>
  </div>
  <p class="note">Themes follow the course categories of <a href="{e(cfg['publisher']['url'])}">{e(cfg['publisher']['name'])}</a>. For catalogues and harvesters: <a href="{root}catalog.json">metadata records (AMB, JSON-LD)</a> and the <a href="{root}sitemap.xml">sitemap</a>.{f' Source files are in the <a href="{e(cfg["repositoryUrl"])}">repository</a>.' if cfg.get('repositoryUrl') else ''}</p>
</main>
<script type="application/json" id="catalogue-data">{json.dumps(data, ensure_ascii=False).replace("</", "<\\/")}</script>
<script src="{root}assets/catalogue.js"></script>
</body>
</html>
"""
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL"))
    ap.add_argument("--out", default=str(ROOT / "_site"))
    a = ap.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    base = (a.base_url or cfg["baseUrl"]).rstrip("/") + "/"
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    shutil.copytree(ROOT / "vendor", out / "vendor")
    shutil.copy(ROOT / "templates" / "site.css", out / "assets" / "site.css")
    (out / ".nojekyll").write_text("")

    shutil.copy(ROOT / "templates" / "catalogue.js", out / "assets" / "catalogue.js")
    cfg_theme_names = {th["slug"]: th["name"] for th in cfg.get("themes", [])}
    items, records, problems = [], [], 0
    for pkg in sorted((ROOT / "sources").glob("*.h5p")):
        slug = pkg.stem
        side_path = pkg.with_suffix(".json")
        side = json.loads(side_path.read_text(encoding="utf-8")) if side_path.exists() else {}
        dest = out / "content" / slug
        safe_extract(pkg, dest)
        h5p = json.loads((dest / "h5p.json").read_text(encoding="utf-8"))
        (out / "downloads").mkdir(exist_ok=True)
        shutil.copy(pkg, out / "downloads" / pkg.name)
        lic = licence_info(h5p, side)
        rows = socle(h5p, side, lic)
        exposed = lic is not None
        tslugs, unknown = themes_of(side, cfg)
        for u in unknown:
            print(f"  WARNING {slug}: Moodle category {u!r} matches no theme in config.json")
        side = {**side, "_themes": [cfg_theme_names[s] for s in tslugs], "_themeRefs": [{"slug": s, "name": cfg_theme_names[s]} for s in tslugs]}
        rec = amb_record(slug, h5p, side, lic, cfg, base)
        rdir = out / "r" / slug
        rdir.mkdir(parents=True)
        (rdir / "index.html").write_text(page_resource(slug, h5p, side, lic, rows, rec, cfg, exposed), encoding="utf-8")
        (rdir / "metadata.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        pdir = out / "preview" / slug
        pdir.mkdir(parents=True)
        content = json.loads((dest / "content" / "content.json").read_text(encoding="utf-8"))
        (pdir / "index.html").write_text(page_preview(slug, h5p, content, side, pkg.stat().st_size, cfg, side["_themes"], head), encoding="utf-8")
        if exposed:
            records.append(rec)
        title = side.get("title") or h5p.get("title")
        kind = H5P_TYPES.get(h5p.get("mainLibrary"), "Interactive content")
        facets = {"format": [kind], "language": [LANGS.get(c, c) for c in rec.get("inLanguage", [])],
                  "audience": side.get("audience", []), "licence": [f"{lic[0]} {lic[1]}" if lic else "Not declared"],
                  "duration": [side["timeRequired"]] if side.get("timeRequired") else []}
        search = " ".join([title, clean(side.get("description", "")), " ".join(side.get("keywords", [])),
                           " ".join(cfg_theme_names.get(s, "") for s in tslugs)])
        items.append({"slug": slug, "title": title, "desc": clean(side.get("description", "")), "lic": lic, "rows": rows,
                      "exposed": exposed, "kind": kind, "lang": rec.get("inLanguage", []), "themes": tslugs,
                      "facets": facets, "search": search})
        print(f"\n{slug}  ({'exposed' if exposed else 'NOT exposed'})")
        for r in rows:
            mark = {"ok": "  ok ", "check": "check", "missing": " MISS"}[r[1]]
            print(f"  [{mark}] {r[0]}" + (f" - {r[2]}" if r[1] != "ok" and r[2] else ""))
            problems += r[1] == "missing"

    (out / "index.html").write_text(page_index(items, cfg), encoding="utf-8")
    theme_urls = []
    for th in cfg.get("themes", []):
        tdir = out / "themes" / th["slug"]
        tdir.mkdir(parents=True)
        (tdir / "index.html").write_text(page_index(items, cfg, root="../../", theme=th["slug"]), encoding="utf-8")
        if any(th["slug"] in it["themes"] and it["exposed"] for it in items):
            theme_urls.append(f"{base}themes/{th['slug']}/")
    (out / "catalog.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    today = dt.date.today().isoformat()
    urls = [base] + theme_urls + [r["id"] for r in records]
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{e(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n", encoding="utf-8")
    print(f"\nBuilt {len(items)} resources ({len(records)} exposed) into {out}  base={base}")
    print(f"{problems} minimum requirement(s) missing across resources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
