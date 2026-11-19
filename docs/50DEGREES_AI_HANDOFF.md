# CivicAlign AI bill explanations and 50degrees — dependency audit

**Audited November 18, 2026.** The separate 50degrees generator has not been inspected; its source, API vendor and publisher URL are still unknown. No AI API calls, paid services, new AI pipeline or production source changes are authorized by this document.

## Confirmed from the current CivicAlign repository and original export README

- Official bill summaries: sourced directly from GovInfo/CRS, no AI key required. The release has official status for 128 bills and CRS summaries for 107; 21 official summaries are unavailable.
- Existing 50degrees input: the command is **civicalign export 119** (a separate installation). The current October 29 export contains 897 floor votes, 128 bills, 537 committee votes and 592 nominations. It records an explanations_prompt_version of p7-2026-10-12, but does not disclose the AI provider.
- The original export README expressly says full AI bill explanations need an API key that was not yet supplied. It has **40 provisional AI-drafted, source-quoted, human-spot-checked key_facts collections**, **88 without checked bill explanations**, and **no approved full AI explanations**. The 40 are not a substitute for fully checked explanations.
- Existing fixed-rule vote Yes/No meanings are already present in export votes.json, while newer roll calls outside the export still lack those explanations.
- The site currently reads a verified import from October 29; it does not automatically generate the 50degrees files. It already has a scheduled HTTPS importer with optional token, hash verification, ID and count checks, fail-closed behavior, source alerts, and independent checks before publishing.
- The project README separately describes Stage 2/2.5 official vote context packets and an experimental Stage 3 Maker/Checker, which is not published. This is not evidence that the separate 50degrees generator has those features.
- The September project blueprint proposes Anthropic Maker and OpenAI Checker as an architecture. This is a proposal, **not** proof of what is actually implemented or which key is needed.
- GitHub Actions uses a data-import variable named CIVICALIGN_DROP_URL and optional data-import secret CIVICALIGN_DROP_TOKEN. Neither is an AI model API key.

## Partner setup (added November 19, 2026)

The ready-to-copy publishing workflow for the generator's own repository is
[`docs/partner/publish-50degrees.yml`](partner/publish-50degrees.yml), explained in
[`docs/50DEGREES_PARTNER_SETUP.md`](50DEGREES_PARTNER_SETUP.md). Before setting `CIVICALIGN_DROP_URL`, try the
address with `python -m civicalign.legislative_sync --check <address>`, which imports nothing.
`tests/test_publisher_chain.py` runs the whole receiving chain over a real HTTP connection with the real export.

## What can be done now, without buying an API key

The new offline preparer at scripts/prepare_50degrees_publish.py takes a fresh output from the **existing** 50degrees generator and builds the exact package format that the receiving importer expects. It does **not** scrape sources, generate explanations, call AI, publish online or use credentials.

On a checkout that can reach the original generator output:

1. Run the existing 50degrees command, as documented by that system, to produce a **fresh** export for Congress 119.
2. From a current CivicAlign checkout run:

   PYTHONPATH=src python scripts/prepare_50degrees_publish.py --source /path/to/50degrees-export --output /path/to/new-publish-folder

3. The preparer checks expected files, readable JSON, declared counts, duplicate IDs, cross-file ID joins and at most 14-day age, then copies the eight original export files and creates the SHA-256 manifest.json. It refuses to overwrite its output.
4. **Owner chooses and approves** a real publisher with a stable HTTPS directory. Publish the prepared files as a complete consistent set, with the manifest last (prefer a versioned directory and an atomically switched current pointer). This must be done by the operator of the actual generator, not an invented external feed.
5. Set GitHub Actions repository variable CIVICALIGN_DROP_URL to the exact approved HTTPS directory. Set Actions secret CIVICALIGN_DROP_TOKEN only if that approved provider requires a bearer token. Never disclose tokens in code, website JS, issues, generated export files or logs.
6. Run the whole workflow on a test branch, verify the legislative sync actually reports a newer imported drop, check all tests and every independent supervisor check, then review the Data checks section before merging.

**Limits:** SHA-256 and consistent IDs only verify transport consistency. They do not prove a bill claim is substantively correct. Model-generated text must remain held or pending until a separate evidence verifier traces every claim to the specific official text version. The 50degrees importer and supervisor remain the real release gates.

## Information needed from the 50degrees operator

Please provide its **non-secret** README, relevant code path, or accessible repository and answer:

1. Where does the command civicalign export 119 run (local folder, another repo, server)? Who operates it? This repo does not contain that generator.
2. Does its full-explanation stage already integrate OpenAI, Anthropic, AWS Bedrock or another service? Which model/SDK and **environment-variable name**? Is any API key already configured? **Never send the key value.**
3. What actually generates bills[].explanations, and what independent claim-level checks set verified or approved vs held? How are exact bill text versions and source quotes hashed and carried forward?
4. Which service can securely publish a fresh export at an approved HTTPS URL on a schedule? What atomic publication, failures, authentication and retention are supported?
5. What is the model token consumption per bill, retries, and expected price for the 88 missing explanations plus incremental new bills? Compare providers only after confirming the existing integration. Set a budget cap before making a paid call.
6. Does the operator have permission to publish these exported records and attribution data?

**Congress.gov API key:** optional, not a prerequisite for the official CRS summaries currently retrieved through GovInfo. Congress.gov offers an independent public data API that requires a free key; add it only if needed for a source or feature currently missing.

**No second AI pipeline:** reuse or finish the current 50degrees generator. The new preparer is an independent packaging helper, not a generator.

## Definition of done

- [ ] Existing 50degrees generator's model/provider and real source location audited.
- [ ] AI provider key necessity and cost estimated, explicit owner-approved budget, no exposed secrets.
- [ ] Trusted publisher approved and scheduled; manifest hashes and atomic files supplied from real 50degrees exports.
- [ ] Importer sees new drop, passes retention/coverage checks and all independent checks in branch CI.
- [ ] Explanation text verifies each claim against the bill text version and is published only when approved; held text never appears as verified.
- [ ] Production workflow finishes, Pages deploy succeeds, site displays updated freshness and explanation coverage.

Until all relevant boxes pass, end-to-end auto-updates and full AI bill explanations remain **BLOCKED**, not completed.
