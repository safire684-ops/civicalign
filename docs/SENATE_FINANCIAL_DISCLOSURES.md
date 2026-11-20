# Senate financial disclosures: net-worth ranges and investment holdings

**Purpose:** Replace the two unhelpful “Not available” rows on individual senator profiles with source-linked public annual financial disclosure estimates and selected investments. No personal account, API key, subscription, or paid model is used.

## What CivicAlign shows

- **Estimated net worth** is the *range* derived from the reported asset and debt value bands, **not** a current dollar measurement or a score of the senator. Some homes, pensions and smaller personal assets are not reportable, so different analysts may calculate different estimates.
- **Stocks held** lists up to eight individually identified stocks *from the source's largest-holdings summary* and up to five named funds/trusts when direct stocks aren't in that summary. **No individual-stock row in a summary does not establish zero stocks** in the full filing. Blind trusts and mutual funds do not disclose the issuer-by-issuer beneficial portfolio.
- Every row links to its source at senatefiles.org and the [official Senate eFD search](https://efdsearch.senate.gov/search/). The filing/report year and filed date are shown when supplied. Transactions filed after an annual report may change holdings; these are not current market positions.

## Data sources and update contract

- **Primary source:** [U.S. Senate Office of Public Records](https://www.senate.gov/legislative/Public_Disclosure/financial-disclosure.htm) and its electronic disclosure search. The source reports value brackets. Public use of disclosures is subject to restrictions under 5 U.S.C. 13107(c); CivicAlign is a public civic information site, not a commercial solicitation or credit service.
- **Public structured summaries:** [Senate Files](https://senatefiles.org/about). Its index of latest senator annual disclosure totals and each senator's largest listed holdings are transcriptions of official reports. The resulting financial records are attributed to Senate Files rather than described as CivicAlign's independently audited exact wealth.
- **Storage:** `data/financials/senate.json`, keyed by seven-character Bioguide ID. The builder publishes the same data to `demo/data/financials.json`. GitHub Pages serves **only static files**. There are no secrets or personal accounts in the website.
- **Schedule:** existing daily GitHub Actions checks whether the financial snapshot is seven days old. If due, `python -m civicalign.financials` checks the public index and linked annual summaries. It will publish a new snapshot only after a minimum of 70 successfully parsed index/report records. On source access failure, schema drift or low coverage, it **keeps the last verified snapshot**; it never fabricates zero holdings or silently substitutes an old filing for a new one.
- **Validation:** tests check parsing, ID matching, year, money range strings, stock/fund distinction, no-key operation and failed-refresh retention; the independent supervisor checks that the page's finance dataset reproduces the attributed source snapshot unchanged.

## Limits and follow-up

This is a secondary public-record transcription. We should also review a sample of individual Senate eFD reports against the summaries, especially when a member's disclosed assets include substantial blind trusts or their home mortgage. Different public trackers exclude home-mortgage debt differently; if the quoted interval conflicts with the filing, hold and correct that entry rather than silently invent a consensus.

If an individual source fails or a senator has no published annual summary, the profile links users to the actual public disclosures and does not claim an exact value or the absence of stock ownership. This is intentional and accurate. Holders may file annual reports, amendments or periodic transactions on different schedules, so “checked this week” is not the same as “holdings as of this week.”

**Budget:** $0 additional; no API tokens, cloud AI, user credentials or private data used. GitHub Actions operates within the user's existing available plan limits.
