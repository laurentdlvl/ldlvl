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
templates/site.css  site styles
vendor/             h5p-standalone 3.8.2 player, unmodified
config.json         site title, publisher, default base URL for local builds
.github/workflows/  builds and deploys to GitHub Pages on every push to main
.zenodo.json        metadata used by the GitHub–Zenodo integration
```

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

## Persistent identifiers

Enable the repository in Zenodo's GitHub integration: each GitHub release is archived with a
DOI, and a concept DOI groups all versions. That DOI identifies the collection. For a DOI per
resource (FAIR-by-Design asks for one per published object), deposit each `.h5p` on Zenodo
separately and record its DOI in the sidecar; the page and metadata will carry it.

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
