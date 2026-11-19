# Connecting the 50degrees generator to CivicAlign (for the 50degrees operator)

CivicAlign already imports, checks and publishes your exports every day. The only missing piece is a fresh
export at a fixed web address. This takes about 15 minutes and needs no CivicAlign credentials.

## What you set up (in the repository that runs `civicalign export 119`)

1. Copy [`docs/partner/publish-50degrees.yml`](partner/publish-50degrees.yml) to
   `.github/workflows/publish-civicalign.yml` in your repository.
2. Edit the step **Run the existing 50degrees export** so it installs and runs your generator exactly as you
   do today. The output folder must hold the same eight files as the October 29 export: `README.md`,
   `meta.json`, `senators.json`, `votes.json`, `positions.json`, `bills.json`, `committee_votes.json`,
   `nominations.json`.
3. In your repository: **Settings → Pages → Source: GitHub Actions**.
4. Run the workflow once by hand (**Actions → Publish the 50degrees export for CivicAlign → Run workflow**).
5. Send the CivicAlign owner the address: `https://<owner>.github.io/<repository>/drops/119/`.

After that it runs every Monday on its own. Your computer doesn't need to be on.

## What the workflow does

- Runs **your** generator. It doesn't generate anything itself.
- Checks the result with CivicAlign's public `scripts/prepare_50degrees_publish.py`. It refuses an export
  that is more than 14 days old, has missing files, counts that disagree, duplicate IDs or broken links
  between files. A refused export publishes nothing, so the last good one stays up.
- Publishes the files plus `manifest.json` (each file's SHA-256) in a single GitHub Pages deploy, so
  CivicAlign never sees a half-updated folder.

## What CivicAlign does with it (already built)

- The owner first tries the address with
  `PYTHONPATH=src python -m civicalign.legislative_sync --check <address>`, which runs every import check
  and imports nothing.
- Then they set it as the repository variable `CIVICALIGN_DROP_URL`. From then on, the daily run imports
  each newer export after checking every file's hash, the counts in `meta.json`, every ID link, and that
  no earlier vote, bill or nomination has disappeared. Anything wrong keeps the last good export.
- The independent supervisor and all tests run before anything is published, and a "CivicAlign data alert"
  issue opens when the legislative data is more than 14 days old.

## Questions only you can answer

1. **AI explanations:** does your pipeline generate the full bill explanations, or only the 40 `key_facts`
   sets? Which provider does it use? If it needs a key, keep it as a secret in **your** repository. Never
   send it to anyone.
2. **Your checker:** how does it decide `verified` versus `held`, and does a person review anything?
3. **Permission:** may CivicAlign publish these records with credit to 50degrees?
4. **Private repository:** if your repository must stay private, GitHub Pages may not be available on your
   plan. Tell the owner, and you can agree another HTTPS host. The importer can send a bearer token
   (`CIVICALIGN_DROP_TOKEN`), which the owner stores as a GitHub secret.
