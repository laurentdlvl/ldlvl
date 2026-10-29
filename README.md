# EDCH open interactive resources

A static site that plays, describes and offers for download H5P learning resources. It runs on
GitHub Pages with no server and no database: an open-source player
([h5p-standalone](https://github.com/tunapanda/h5p-standalone)) displays each package in the
browser, and a build script generates the pages, the catalogue and the metadata.

Prototype for AEGIS-OA WP3, Task 3.3 (D3.2): an existing-components route for exposing H5P
content outside Moodle, while Moodle remains the place for tracked learning.

## What the site provides

| For | What |
|---|---|
| Learners and teachers | A page per resource with the interactive player, licence, author and reuse instructions |
| Reusers | The `.h5p` package to download and import into Moodle, another H5P-enabled platform, or an H5P editor |
| Catalogues and harvesters | Dublin Core and citation tags in each page, AMB-compatible JSON-LD, `catalog.json` (all records), `sitemap.xml`, `robots.txt` |
| Authors | A check of each resource against the minimum set (OER definition plus FAIR-by-Design minimum elements), in the build log and on each page |

Only resources with a declared Creative Commons licence are exposed for harvesting. Others are
shown, marked `noindex`, left out of the sitemap and catalogue, and cannot be downloaded.

## Repository layout

```
sources/            one .h5p package per resource, plus an optional <slug>.json sidecar
scripts/build.py    builds the site into _site/ (Python standard library only)
scripts/zenodo_deposit.py  deposits each resource on Zenodo (one DOI per resource)
templates/site.css  site styles
vendor/             h5p-standalone 3.8.2 player, unmodified
config.json         site title, publisher, default base URL for local builds
.github/workflows/  pages.yml: build and deploy on every push; zenodo.yml: Zenodo deposit, run by hand
```

## Themes, search and filters

The catalogue has one tab and one page per theme (`themes/<slug>/`). Themes are the course
categories of EDCH Training, listed in `config.json` (`themes`). Each resource takes its theme
from the `moodleCategory` field of its sidecar (a name, or a list of names, exactly as in
`config.json`); the build warns about names it does not know. When resources are imported from
Moodle, this field will be filled from the course category.

Search (title, description, keywords, theme) and filters (format, language, audience, licence,
time required) run in the browser. A filter with a single value is hidden. The search and
filters are kept in the page address, so a filtered view can be shared as a link.

## Import preview

Each resource also has an **import preview** (`preview/<slug>/`, not indexed), linked from its
page. It lists every field the page would show once resources are imported from Moodle, with
its source: the H5P package, the build (computed from the package), the Moodle activity, the
Moodle course, Zenodo or the site. Moodle fields stay empty until the import exists; values
typed by hand in the sidecar are shown only as placeholders to be replaced.

## Add a resource

1. Export the content as an `.h5p` file (Moodle content bank, H5P editor, Lumi).
2. Save it as `sources/<slug>.h5p`. The slug becomes the page address, e.g. `r/<slug>/`.
3. Copy an existing sidecar to `sources/<slug>.json` and fill in what the package does not
   carry: description, learning objectives, prerequisites, time required, accessibility
   statement, DOI once deposited. Text starting with `[draft]` is flagged for validation.
4. Commit and push. The workflow rebuilds and republishes the site.

The licence and author are read from the package (`h5p.json`). Set them in the authoring tool
where possible; a `licence` field in the sidecar (e.g. `"CC BY 4.0"`) overrides the package.

## Publish

1. Create a repository and push these files to `main`.
2. In **Settings → Pages**, set **Source** to **GitHub Actions**.
3. The first push builds the site at `https://<owner>.github.io/<repository>/`. The base URL
   used in metadata and the sitemap is set automatically by the workflow.

Build locally: `python3 scripts/build.py --base-url http://localhost:8000/`, then
`python3 -m http.server 8000 -d _site`. The player needs to be served over HTTP; opening the
files directly from disk does not work.

## Persistent identifiers (Zenodo)

The **Deposit on Zenodo** workflow gives each resource its own Zenodo record and DOI.
Run it from **Actions → Deposit on Zenodo → Run workflow**.

- **First deposit** creates the record. **Later deposits** happen only when the `version`
  in the sidecar changes, and create a new version of the same record, so all versions share
  one *concept DOI* (the "all versions" identifier).
- The identifiers are written back into `sources/<slug>.json` under `zenodo.<target>` and
  committed by the workflow.
- **Targets.** `sandbox` (sandbox.zenodo.org) is for tests: DOIs are fake and are never shown
  on the site. `production` (zenodo.org) mints real DOIs, copies them to the `doi` and
  `conceptDoi` fields, and rebuilds the site so pages and metadata carry them.
- **Gate.** A resource is skipped without a Creative Commons licence or an author, and on
  production while its description is still marked `[draft]`.

Secrets (Settings → Secrets and variables → Actions): `ZENODO_SANDBOX_TOKEN` for the sandbox,
`ZENODO_TOKEN` for production. Create each token on the matching Zenodo site under
Account → Applications → Personal access tokens, with the scopes `deposit:write` and
`deposit:actions`.

Local check without sending anything: `python3 scripts/zenodo_deposit.py --target sandbox --dry-run`.

The GitHub–Zenodo release integration (one DOI for the whole repository) is not needed and
should stay off, to avoid a second, overlapping record.

## Limits

- **No learner tracking.** Results are not saved. The player emits xAPI statements in the
  browser, but nothing collects them. Use Moodle for tracked learning and certificates.
- **No online editing.** Edit in an H5P editor, export, and replace the package.
- **Size.** GitHub Pages sites are limited to about 1 GB and files to 100 MB. Host heavy video
  elsewhere (for example PeerTube) and link it from the content.
- **Compatibility.** The standalone player supports most H5P content types; check new types
  locally before publishing.
- **Hosting.** GitHub is a commercial service outside the EU. Zenodo archiving mitigates the
  risk; a public GitLab instance with Pages is an alternative.

## Current resources

| Slug | Licence | Note |
|---|---|---|
| `doas-choosing-a-platform` | CC BY 4.0 | Description drafted, to validate |
| `doas-edib` | CC BY 4.0 | Description drafted, to validate |
| `doas-copyright-and-licences` | Not declared | Package declares no licence and no author; not exposed until fixed |

Packages by DIAMAS. Player: h5p-standalone (MIT), by Tunapanda and contributors.
