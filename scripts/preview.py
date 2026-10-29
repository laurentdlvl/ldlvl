"""Import preview: what a page would show once resources are imported from Moodle.

Each field is labelled with the source it would come from:
  package   h5p.json and content.json inside the .h5p file (read now)
  computed  derived from the package by the build (computed now)
  activity  the H5P activity settings form in Moodle (not imported yet)
  course    the Moodle course that contains the activity (not imported yet)
  zenodo    the Zenodo deposit (after deposit)
  site      config.json of this site
Nothing is invented: a Moodle field shows no value until the import exists. Where the
sidecar currently holds a hand-written value, it is shown as a placeholder to be replaced.
"""
import html
import json
import re

e = lambda s: html.escape(str(s), quote=True)

SOURCES = {
    "package": ("H5P package", "h5p.json / content.json, filled in the H5P editor (Metadata button, media credits)"),
    "computed": ("Computed", "derived from the package by the build, no input needed"),
    "activity": ("Moodle activity", "settings form of the H5P activity"),
    "course": ("Moodle course", "settings of the course that contains the activity"),
    "zenodo": ("Zenodo", "deposit workflow"),
    "site": ("Site", "config.json of this site"),
}
STATUS = {"filled": "Filled", "missing": "Missing", "pending": "Awaiting import", "partial": "Partial", "deposit": "Awaiting deposit"}

QUESTIONS = {"H5P.MultiChoice", "H5P.TrueFalse", "H5P.DragText", "H5P.Blanks", "H5P.MarkTheWords",
             "H5P.DragQuestion", "H5P.SingleChoiceSet", "H5P.Summary", "H5P.Essay", "H5P.ImageHotspotQuestion"}
OTHER_INTERACTIONS = {"H5P.Dialogcards": "flashcards", "H5P.Accordion": "accordions",
                      "H5P.ImageHotspots": "image hotspots", "H5P.Flashcards": "flashcards"}
TEXT_KEYS = {"text", "question", "textField", "answer", "tip", "statement"}
ROLES_NOTE = {"Licensee": "licensee", "Author": "author", "Editor": "editor", "Translator": "translator",
              "Licensee ": "licensee", "Creator": "creator", "Contributor": "contributor"}


def _words(s):
    return len(re.sub(r"<[^>]+>|&nbsp;|&[a-z]+;", " ", s).split())


def analyse(content, h5p):
    """Walk content.json and return derived facts."""
    libs, words = {}, 0
    images = alt = 0
    credits_total = credits_filled = 0
    questions, other = 0, {}

    def walk(o, lib=None):
        nonlocal words, images, alt, credits_total, credits_filled, questions
        if isinstance(o, dict):
            name = o.get("library", "").split(" ")[0] if isinstance(o.get("library"), str) else None
            if name:
                libs[name] = libs.get(name, 0) + 1
                md = o.get("metadata") or {}
                if name in ("H5P.Image", "H5P.Video", "H5P.Audio"):
                    credits_total += 1
                    if (md.get("license") not in (None, "", "U")) or md.get("authors") or md.get("source"):
                        credits_filled += 1
                if name == "H5P.Image":
                    images += 1
                    if str((o.get("params") or {}).get("alt", "")).strip():
                        alt += 1
                if name in QUESTIONS:
                    questions += 1
                if name in OTHER_INTERACTIONS:
                    other[OTHER_INTERACTIONS[name]] = other.get(OTHER_INTERACTIONS[name], 0) + 1
            for k, v in o.items():
                if isinstance(v, str) and k in TEXT_KEYS:
                    words += _words(v)
                else:
                    walk(v, name or lib)
        elif isinstance(o, list):
            for v in o:
                walk(v, lib)

    walk(content)
    if "chapters" in content:
        units = ("chapters", [(ch.get("metadata") or {}).get("title", "") for ch in content["chapters"]])
    elif "presentation" in content:
        units = ("slides", [f"Slide {i + 1}" for i in range(len(content["presentation"].get("slides", [])))])
    else:
        units = ("parts", [])
    minutes = round(words / 200 + questions)
    return {"units": units, "words": words, "images": images, "alt": alt, "questions": questions,
            "other": other, "credits": (credits_filled, credits_total), "minutes": minutes, "libs": libs}


def row(label, value, source, status, where="", placeholder=""):
    return {"label": label, "value": value, "source": source, "status": status, "where": where,
            "placeholder": placeholder}


def _ph(side, key):
    v = side.get(key)
    if isinstance(v, list):
        v = ", ".join(x if isinstance(x, str) else x.get("name", "") for x in v)
    v = str(v or "").strip()
    return v[len("[draft]"):].strip() if v.startswith("[draft]") else v


def build_rows(h5p, side, facts, size, cfg, theme_names):
    f = facts
    lic = h5p.get("license", "U")
    authors = [a for a in h5p.get("authors", []) if a.get("name")]
    years = "–".join(str(y) for y in (h5p.get("yearFrom"), h5p.get("yearTo")) if y)
    lang = h5p.get("language", "und")
    utype, unames = f["units"]
    cf, ct = f["credits"]
    other = ", ".join(f"{n} {k}" for k, n in f["other"].items())
    groups = [
        ("Identity and description", [
            row("Title", "", "activity", "pending", "Activity name", _ph(side, "title")),
            row("Title in the package", h5p.get("title", ""), "package", "filled" if h5p.get("title") else "missing",
                "H5P editor, Title (fallback if the activity name is empty)"),
            row("Summary", "", "activity", "pending", "Description, first paragraph", _ph(side, "description")),
            row("Learning objectives", "", "activity", "pending", "Description, heading “Learning objectives”", _ph(side, "learningObjectives")),
            row("Prerequisites", "", "activity", "pending", "Description, heading “Prerequisites”", _ph(side, "prerequisites")),
            row("Audience", "", "activity", "pending", "Description, heading “Audience”", _ph(side, "audience")),
            row("Duration (declared by the author)", "", "activity", "pending", "Description, heading “Duration”", _ph(side, "timeRequired")),
            row("Keywords", "", "activity", "pending", "Tags", _ph(side, "keywords")),
            row("Resource key", "", "activity", "pending", "ID number (stable across course versions)"),
            row("Language", "" if lang == "und" else lang, "package", "missing" if lang == "und" else "filled",
                "H5P editor, Metadata, Language (currently “undetermined”)"),
        ]),
        ("Rights and attribution", [
            row("Licence", f"{lic} {h5p.get('licenseVersion', '')}".strip() if lic != "U" else "",
                "package", "filled" if lic != "U" else "missing", "H5P editor, Metadata, License"),
            row("Authors and roles", ", ".join(f"{a['name']} ({ROLES_NOTE.get(a.get('role', ''), a.get('role', '').lower())})" for a in authors),
                "package", "filled" if authors else "missing", "H5P editor, Metadata, Authors"),
            row("Years", years, "package", "filled" if years else "missing", "H5P editor, Metadata, Years (from, to)"),
            row("Original source", h5p.get("source", ""), "package", "filled" if h5p.get("source") else "missing",
                "H5P editor, Metadata, Source"),
            row("Change log", "; ".join(c.get("log", "") for c in h5p.get("changes", [])), "package",
                "filled" if h5p.get("changes") else "missing", "H5P editor, Metadata, Changes"),
            row("Media credits", f"{cf} of {ct} images and videos credited" if ct else "No images or videos",
                "package", "filled" if ct == 0 or cf == ct else ("partial" if cf else "missing"),
                "H5P editor, metadata of each image or video"),
        ]),
        ("Content (computed from the package)", [
            row("Format", {"H5P.InteractiveBook": "Interactive book", "H5P.CoursePresentation": "Course presentation", "H5P.InteractiveVideo": "Interactive video", "H5P.QuestionSet": "Quiz"}.get(h5p.get("mainLibrary"), h5p.get("mainLibrary", "")), "computed", "filled"),
            row(f"Structure ({len(unames)} {utype})", "; ".join(unames) if utype == "chapters" else f"{len(unames)} {utype}", "computed", "filled"),
            row("Exercises", f"{f['questions']} scored questions" + (f", plus {other}" if other else ""), "computed", "filled"),
            row("Text volume", f"about {f['words']:,} words".replace(",", " "), "computed", "filled"),
            row("Estimated duration", f"about {f['minutes']} min (reading at 200 words/min, plus 1 min per question)", "computed", "filled",
                "Rule-based estimate, shown only if the author declares no duration"),
            row("Images with a text alternative", f"{f['alt']} of {f['images']}" if f["images"] else "No images", "computed",
                "filled" if f["images"] == 0 or f["alt"] == f["images"] else ("partial" if f["alt"] else "missing")),
            row("Technical requirements", f"Any H5P-enabled platform; package {size / 1e6:.1f} MB, "
                f"{len(h5p.get('preloadedDependencies', []))} H5P libraries included", "computed", "filled"),
        ]),
        ("Context", [
            row("Theme", "", "course", "pending", "Course category", ", ".join(theme_names)),
            row("Part of course", "", "course", "pending", "Course full name and link", _ph(side, "isPartOf")),
            row("Version", "", "course", "pending", "Course version in which the activity last changed", _ph(side, "version")),
            row("Release status", "", "course", "pending", "Course visible and status “published”"),
            row("Publisher", cfg["publisher"]["name"], "site", "filled"),
            row("Access", "Open, no login", "site", "filled"),
        ]),
        ("Persistent identifiers", [
            row("DOI of this version", "", "zenodo", "deposit", "Assigned at deposit (sandbox test done, not shown)"),
            row("DOI for all versions", "", "zenodo", "deposit", "Concept DOI, shared by all versions"),
        ]),
    ]
    return groups


def page_preview(slug, h5p, content, side, size, cfg, theme_names, head):
    root = "../../"
    facts = analyse(content, h5p)
    groups = build_rows(h5p, side, facts, size, cfg, theme_names)
    allrows = [r for _, rows in groups for r in rows]
    count = lambda pred: sum(1 for r in allrows if pred(r))
    by_src = {s: count(lambda r, s=s: r["source"] == s) for s in SOURCES}
    filled_now = count(lambda r: r["status"] in ("filled", "partial"))
    to_fix = [r for r in allrows if r["source"] == "package" and r["status"] in ("missing", "partial")]
    pending = count(lambda r: r["status"] in ("pending", "deposit"))
    title = h5p.get("title", slug)

    legend = "".join(f'<li><span class="src {k}">{e(v[0])}</span> <span class="note">{e(v[1])}</span></li>' for k, v in SOURCES.items())
    sections = []
    for gname, rows in groups:
        trs = []
        for r in rows:
            val = e(r["value"]) if r["value"] else '<span class="empty">—</span>'
            if r["placeholder"]:
                val += f'<br><span class="placeholder">Placeholder written by hand today, to be replaced: “{e(r["placeholder"][:220])}{"…" if len(r["placeholder"]) > 220 else ""}”</span>'
            where = f'<br><span class="note">{e(r["where"])}</span>' if r["where"] else ""
            trs.append(f'<tr><th scope="row">{e(r["label"])}</th><td>{val}</td>'
                       f'<td><span class="src {r["source"]}">{e(SOURCES[r["source"]][0])}</span>{where}</td>'
                       f'<td><span class="st {r["status"]}">{STATUS[r["status"]]}</span></td></tr>')
        sections.append(f"""<section class="pv-group"><h2>{e(gname)}</h2>
  <div class="tablewrap"><table class="pv">
    <thead><tr><th scope="col">Field</th><th scope="col">Value</th><th scope="col">Source, and where it is entered</th><th scope="col">Status</th></tr></thead>
    <tbody>{''.join(trs)}</tbody>
  </table></div></section>""")

    fix = "".join(f"<li>{e(r['label'])}: {e(r['where'])}</li>" for r in to_fix)
    out = head(f"Import preview: {title}", "Where each field of this resource page would come from.",
               '<meta name="robots" content="noindex">\n').replace("{root}", root)
    out += f"""<header class="site"><a class="home" href="{root}">{e(cfg['siteTitle'])}</a></header>
<main class="preview">
  <p class="kind">Import preview · <a href="{root}r/{slug}/">current page</a></p>
  <h1>{e(title)}</h1>
  <p class="lede">What this resource’s page would show once it is imported from EDCH Training. Each field is labelled with its source. Moodle fields stay empty until the import exists; nothing below is invented.</p>
  <dl class="facts pv-sum">
    <div><dt>Filled now</dt><dd>{filled_now} of {len(allrows)} fields, from the package, the build and the site</dd></div>
    <div><dt>Awaiting the Moodle import</dt><dd>{pending} fields ({by_src['activity']} from the activity, {by_src['course']} from the course, {by_src['zenodo']} from Zenodo)</dd></div>
    <div><dt>To fix in the H5P editor</dt><dd>{len(to_fix)} field{'s' if len(to_fix) != 1 else ''}</dd></div>
  </dl>
  {f'<details open><summary>To fix in the H5P editor before import</summary><ul>{fix}</ul></details>' if fix else ''}
  <details><summary>Sources</summary><ul class="legend">{legend}</ul></details>
  {''.join(sections)}
  <p class="note">Values computed from the package are recalculated at each build. The estimated duration is a rule of thumb, not a substitute for the author’s figure.</p>
</main>
</body>
</html>
"""
    return out
