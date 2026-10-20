---
name: ezfeed-exports
description: Get feeding records out of EZfeed (Valley Ag Software's feed management program) as CSV report exports and read them - each pen's daily intake by feed (called for and fed), the pen summaries with head counts and cost, the recipes, feeder loads and refusals. Use when someone asks how to export from EZfeed, which EZfeed reports to save, hands over EZfeed reports, or asks about a pen's intake, recipe, loading or refusals from EZfeed.
license: CC-BY-4.0
---

# EZfeed exports

EZfeed records what each pen was called for and fed, feed by feed and day by day. The kit reads its printed reports
saved as CSV. Report names and menus can differ between EZfeed versions: find the report by its name below and check
its column headings.

## The reports

| Report in EZfeed | What it gives | Needed for |
| --- | --- | --- |
| Ingredient Intake Tgt vs Act by Pen | each pen, feed and day: dry matter called for and fed (lb per head), cost | ration change, loading accuracy, pen feed |
| Pen Summary (Milking Cows), (Dry Cows), (Heifers) | each pen and day: dry matter and cost per head, EZfeed's head count, first feeding time | pen feed (per DairyComp head), consistency |
| Rations (current breakdown) | each recipe today: as fed and dry matter lb, DM %, $ a ton | the recipe and its cost |
| Ingredient Intake by Ration | each recipe, feed and day | recipes fed to several pens |
| FeederLoad Summary | each feeder's loads: deviation from target | loading accuracy by feeder |
| Refusal Summary | each pen and day: refused, % of delivered | refusals |

Set the date range as long as the question needs: last year's same weeks as well make the season check possible.
Save them into the same folder as the DairyComp files, named however you like:

```
python scripts/dairy.py files --folder "Farm Exports"
```

lists each file and what it was recognised as (by its column headings, which EZfeed prints the same on every farm).
If a report isn't recognised, show the person its first five lines and say which report it seems to be; don't guess
at columns.

## What to watch for

- **Rows nest**: a pen row, then its feeds, then a row per day; only the day rows are facts, the rows above them are
  subtotals. Reports overlap (a rolling window): where two files have the same day, the newer file wins.
- **Pen names**: EZfeed's "Pen 21" is DairyComp's pen 21; a pen only EZfeed has (hospital, beef) stays unmatched.
- **Head counts**: EZfeed's can be well off; the kit uses DairyComp's count for per-cow figures.
- **Fed is delivered, not eaten.** All-zero refusals or all-zero milk columns mean not measured here, never zero.
- **Premixes** appear as themselves and as their parts: counted once.
- **Prices are the farm's own.** If some are blank or zero, feed cost is incomplete: say so, never price a feed at $0.
- Negatives print in brackets, `($7.39)`; refusals print negative and are read as amounts.

Pounds of dry matter per cow a day, and dollars per cow a day. Name the reports and their dates.
