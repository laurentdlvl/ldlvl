# Course archives

One folder per course archived on Zenodo. Each folder holds only the deposit description;
the files themselves (Moodle backup, extracted resources) are too large for this repository
and are uploaded by hand in the Zenodo form.

```
courses/<course>/
├── zenodo-metadata.json   description of the Zenodo record, edited here
└── zenodo-draft.json      written by the workflow: record id, reserved DOI, edit link
```

## Create a draft

1. Edit `courses/<course>/zenodo-metadata.json` and fill every `{{TO_COMPLETE}}`.
2. Run **Actions → Zenodo course draft → Run workflow**, with the course folder and the target
   (`sandbox` first). The workflow creates the draft, reserves its DOI, and commits
   `zenodo-draft.json`. It never uploads files and never publishes.
3. Open the edit link from `zenodo-draft.json` (also shown in the run summary):
   - write the reserved DOI into the README of the deposit, then upload the files listed in
     `files_to_upload`;
   - set `README.md` as the default preview;
   - add funding (search the EU grant list for CRAFT-OA and AEGIS-OA) and the community;
   - optionally move the module list and technical notes into typed "Additional descriptions"
     (Table of contents, Technical info);
   - preview, then publish.

On sandbox only, the workflow option *allow_placeholders* lets you test with placeholders left.
A second run for the same course and target does nothing while a draft is recorded.

Uses the same secrets as the resource deposit: `ZENODO_SANDBOX_TOKEN`, `ZENODO_TOKEN`.
Local check without sending anything:
`python3 scripts/zenodo_course_draft.py --course xml-publishing --target sandbox --dry-run`.
