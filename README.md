# Dairy Data Tools

Free tools for dairy nutritionists and their AI agents. Give your agent a farm's own **DairyComp** and **EZfeed**
exports and ask about a pen: how it's doing, what a ration change did, and whether it's just the season. The numbers
come from small, tested scripts, not from the AI's guesswork.

By Pádraig Lucey, MVB, MPVM, Ph.D. ([Dairy Data Science](https://dairydatascience.com)).

## Get it

**In the Claude app** (desktop or claude.ai, a paid plan with code execution on): Customize > Plugins > Add marketplace >
`padge01/dairy-data-tools`, then Add **Dairy Data Tools**. Attach the farm's export files to a chat and ask.

**In Claude Code:**

```bash
claude plugin marketplace add padge01/dairy-data-tools
```

```bash
claude plugin install dairy-data-tools@dairy-data-tools
```

**In other agents** (Codex, Cursor, Gemini CLI and others that read Agent Skills):

```bash
npx skills add padge01/dairy-data-tools
```

**In Python, without an agent** (Python 3.10 or later; nothing else to install):

```bash
pip install dairy-data-tools
```

```bash
dairy-data-tools pen --folder "Farm Exports" --pen 21
```

Every question has a command: `dairy-data-tools --help` lists them. The ration change is `dairy-ration-change`.

## What's in it

Ask in plain words; the right skill picks itself. No commands to learn.

| Skill | Ask it | What it does |
| --- | --- | --- |
| dairycomp-exports | "How do I get my cow list out of DairyComp?" "Write me a list of fresh cows in pen 1." "Which of these items shouldn't I use?" | The reports to save for this farm; DairyComp commands from plain English, checked against the farm's own items (SHOW, never LIST, which prints); what each item is |
| ezfeed-exports | "Which EZfeed reports do you need?" | The reports to save and how they're read |
| herd-explorer | "How is pen 21 doing?" "What happened to cow 1100?" | The herd, every pen, one pen, one cow: milk and ECM as a spread, events, lactations |
| pen-feed | "What's pen 21's feed efficiency and IOFC?" "Is the feed loaded as called for?" | Each pen's cows joined to its feed: intake per cow, ECM per lb DM, cost per cwt, IOFC, NASEM's predicted intake; loading accuracy, refusals, consistency |
| weekly-review | "Get me ready for Thursday's visit." "How are the fresh cows doing?" | Fresh cows, components and MUN, udder health, reproduction, who left, the pens' feed, and actions for the next visit |
| ration-change | "Did pen 21's ration change work, or is it the season?" | The week before against the latest week, with the same weeks last year or another pen taken out |
| balance-ration | "Balance pen 21's ration" | The free Dairy Ration Lab when it's connected; this kit never makes up a ration |

Built on the Rossow Data Lab, teaching tools the author wrote for Heidi Rossow's lab at UC Davis, ported to plain
Python: every count says what it's out of,
milk is shown as a spread, and the farm is compared with itself, never with published targets.

**A sample herd** (`sample-herd/`): a made-up California dairy's exports, to try every skill before using a real farm's.

**Its neighbours**, separate tools from the same place: **BESTPRED** (USDA's best prediction of 305-day and
mature-equivalent milk; in this marketplace, and at `https://bestpred.dairydatascience.com/mcp`) and the **Dairy Ration
Lab** (a free ration balancer).

## What it does with your files

- The scripts read the export files where they are. They change nothing, keep nothing, and send nothing over the
  internet. They use Python's standard library only.
- In Claude's chat the files you attach and the scripts run in Claude's own code sandbox. What the agent reads goes to
  the AI company as part of the conversation, as anything you attach does, unless you run a model on your own computer.
- Event remarks, protocols and technician names are left out of what the scripts report, because they are free text
  typed on the farm and could contain anything, including instructions aimed at an agent.
- Nothing reads DairyComp's own files or backups, and no figure DairyComp calculates for itself (such as 305-day or
  mature-equivalent milk) is used: the kit works from raw records.

## Good to know

- Weights are in pounds. Pens are compared with themselves and with the farm's other pens, never with published
  targets.
- It's a teaching and planning tool, not veterinary or nutrition advice: check anything before it changes what cows are
  fed.
- DairyComp 305 and EZfeed are Valley Ag Software's products; this project isn't affiliated with them.

## Cite it

If it helps your work, please cite it: GitHub's "Cite this repository" button gives the reference (`CITATION.cff`).

## Licence

Code under Apache-2.0 (`LICENSE`); the skills' text under CC BY 4.0 (`LICENSE-skills.md`). Questions and fixes:
[issues](https://github.com/padge01/dairy-data-tools/issues).

## Working on it

- `plugins/dairy-data-tools/`: the plugin people install (skills, sample herd, README, licences).
- `tools/dairy.py`, `tools/dairytools/` and the ration-change scripts in `tools/`: the one copy of the code;
  `python tools/sync_scripts.py` copies it into each skill and writes this README. `pyproject.toml` builds the same
  code as the `dairy-data-tools` package on PyPI.
- `tools/make_sample_herd.py`: writes the sample herd (fixed seeds, same files every run).
- `tests/`: `python -m pytest -q tests` (made-up files with known answers, the sample herd, the directory's file limits).
