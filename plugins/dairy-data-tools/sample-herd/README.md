# Sample herd

A made-up California dairy's exports, for trying every skill. **Not a real farm**: it comes from the author's
herd simulator, with a ration-change story laid over it by `tools/make_sample_herd.py` in the repository.

| File | What it is | From |
| --- | --- | --- |
| `cows_2026-10-28.csv`, `tests_2026-10-28.csv` | Every animal on 28 Oct 2026 (in the herd, sold and dead), and each cow's tests | DairyComp SHOW reports, saved as CSV |
| `tests_2025-12-28.csv` ... `tests_2026-09-28.csv` | The same test report saved each month for ten months: together, each cow's tests over her lactation | DairyComp SHOW reports, saved monthly |
| `events_*.csv` | Three years of events, one file a year | DairyComp EVENTS |
| `items.csv` | The farm's item list | DairyComp ALTER\2 export |
| `intake_2026-08-15_2026-10-28.csv`, `intake_2025-08-15_2025-10-31.csv` | Each pen's daily feed, this fall and last | EZfeed Ingredient Intake Tgt vs Act by Pen |
| `Pen Summary (Milking Cows).csv`, `Pen Summary (Dry Cows).csv` | Each pen's daily intake, cost and head count | EZfeed |
| `FeederLoad Summary.csv`, `Refusal Summary.csv` | Loading by feeder; refusals | EZfeed |
| `rations_2026-10-28.csv` | Today's recipes | EZfeed Rations |
| `pen_milk.csv` | Pens 11 and 21's milk, fat and protein by day, both falls | what `pen_milk.py` makes from daily cow reports |
| `event_map.csv` | What this farm's own event codes mean | written once for the farm |

The story: on 28 Sep 2026 pen 21 (older cows) went onto the new corn silage pile, with more canola meal, half a pound
more bypass fat and half a pound less rolled corn, as the heat lifted. Pen 11 (first lactation) kept its recipe. Try:

- "How is pen 21 doing?" and "What's pen 21's feed efficiency and IOFC at $21.50 milk?"
- "Did pen 21's ration change on 28 Sep work, or is it just the season?"
- "Get me ready for a visit: fresh cows, components, mastitis, pregnancy rate."
- "Write me a DairyComp command for the cows in pen 21 under 60 days in milk."
