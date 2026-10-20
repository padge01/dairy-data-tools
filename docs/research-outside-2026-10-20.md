# Outside research, 20 Oct 2026: plugin patterns and what nutritionists analyse

Summary of a web search (sources linked). Published targets below are context only: the kit never shows them as
benchmarks; it compares a farm with its own history and its other pens.

## Patterns worth copying
- **Anthropic financial-services** (github.com/anthropics/financial-services): vertical plugins with `skills/`, short
  `commands/` (`/comps`: one-line description, `argument-hint`, asks if no argument, calls the skill, delivers a file and
  a summary), single-job read-only agents (`gl-reconciler`: what you produce, a 5-step workflow, guardrails, "for human
  review"), a `scripts/check.py` linter. Skills state data-source priority and output conventions, end with red flags
  and an output checklist.
- **knowledge-work-plugins / data** (`validate-data`): a QA gate with a fixed verdict (Ready / Caveats / Needs
  revision) and named pitfalls (average of averages, denominator shifting); a context-extractor skill that records a
  domain's names once.
- **dbt agent skills**: decision flow, quick reference, "Red flags - STOP", "Common mistakes", evals for A/B testing.
- **MotherDuck**: skills work without the MCP; credentials never in skill files; starter prompts shown to users.

Fits for the kit: commands per weekly job; a read-only analyst agent ending "for nutritionist review"; units and
"per cow" rules inside skills; every figure cites file, date range and cow count; a QA check (cows fed vs cows on the
list, partial weeks, missing days); red-flag sections ("one week of milk doesn't prove a ration change"); a farm-context
skill (pen names, milk price, item names) recorded once; a linter and a changelog.

## Analyses nutritionists use most (synthesis)
1. Feed efficiency (ECM/DMI) and DMI by pen, as a trend (Penn State).
2. IOFC and feed cost per cwt, by group from batch weights (Penn State: feed ~55% of milk income).
3. Fresh cow health: DA, ketosis, metritis, RP, milk fever as cases per fresh cow per month; recording varies by herd.
4. Early removals by 30 and 60 DIM.
5. Week 4 milk and first-test milk by lactation group (agproud: `GRAPH W4MK FOR LACT=2 FDAT>-365\RL BY FDAT`).
6. First-test fat:protein ratio as a herd ketosis screen (Oetzel; UW KetoMonitor).
7. Peak milk and peak ratio by parity (Kentucky; Penn State).
8. Feeding accuracy and shrink (UC Davis, 26 California dairies on FeedWatch: >2% deviations in 46% of loads;
   errors concentrated in alfalfa hay, corn silage, canola).
9. Refusals, as rolling means (very variable day to day).
10. Forage DM changes and ration correction (don't reformulate on one wet sample).
11. MUN and components by pen and DIM.
12. Close-up: days in pen, density, bunk space, moves.
13. Heat stress (THI) against pen milk and DMI: needs weather, which no herd or feed file carries.
14. Pen stocking and moves.

## Verified DairyComp syntax (VAS help, dc-help.vas.com)
Command word, items, `FOR` conditions, `BY`/`DOWNBY`, `\` switches; e.g.
`LIST ID PEN LACT DIM DCC MILK FOR LACT>0 DCC>220 DDAT=0 BY PEN \B2`. Commands: SUM, LIST/SHOW, GRAPH, EGRAPH, EVENTS,
PLOT, BREDSUM, ECON, MONITOR, PCT, FILEOUT, ALTER. Event codes not confirmed by a public source.

## Others
- Nexa Labs' Daisy: free beta, writes DairyComp macros from plain English, from exported files (launch coverage only).
- Ever.Ag's Everett: processing plants, not farms.

## Gaps no public tool covers
Feed-system exports parsed and checked (no public EZfeed/TMR Tracker/FeedWatch field lists); herd and feed joined by pen
and date (FE, IOFC, MUN by pen); a check of how a farm records events before rates are computed; stated definitions on
every card; trends against the farm's own history; forage DM changes linked to fat and DMI over the next 3-7 days;
file, date range and cow count on every output.
