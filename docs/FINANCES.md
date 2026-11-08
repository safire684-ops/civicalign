# Senator finances: what we found (2026-11-08)

**Result: not shown yet.** The profile keeps "Not available" for net worth and stock holdings until the user decides
how, or whether, to use the official Senate source.

## The official source
- Senators file yearly financial disclosure reports and stock trade reports (Periodic Transaction Reports) with the
  Senate. They're published on the Senate's eFD search site, efdsearch.senate.gov.
- The site opens only after the reader ticks a box agreeing to the legal limits on obtaining and using the reports
  (5 U.S.C. 13107(c)). They may not be used for a commercial purpose (news media excepted), to set a credit rating,
  or to raise money for any cause. A daily robot would have to agree each time on someone's behalf. **That's a
  decision for the project owner, and possibly a lawyer, not something the pipeline should do on its own.**
- There's no official bulk download or API. Electronic filings are web tables; paper filings are scanned images.
- Values are ranges set by law ($1,001 to $15,000, $15,001 to $50,000, and so on up to "over $50,000,000"). A
  spouse's separate assets above $1,000,000 can be reported only as "over $1,000,000". A senator's home and its
  mortgage are left out. **No exact net worth exists anywhere official.**
- Trade reports are due within 45 days of the trade. A trade doesn't show what is owned today.

## Other sources
- OpenSecrets: closed new API sign-ups in April 2025; its data is licensed for non-commercial use with share-alike.
- Senate Stock Watcher: abandoned (last update March 2021), no licence.
- Roll Call's "Wealth of Congress": last edition found is 2018-2019.
- Capitol Trades, Quiver Quantitative, Unusual Whales: commercial; republishing would need written permission.
- The House Clerk publishes yearly bulk files, but only for House members.

## If the user approves using eFD
Show only what the filing says, labelled with its year and filing date:
- "Reported assets minus liabilities: $X to $Y", the low end from minimum assets minus maximum liabilities and the
  high end from maximum assets minus minimum liabilities. Any open-ended range makes the high end "no upper limit".
- Each holding with its range and owner (self, spouse, joint, child). Each trade with date, asset, buy or sell,
  range and owner, plus "a trade doesn't show what is owned today".
- Amended reports replace originals; paper filings stay "Not available" unless read by a person.
