"""Dairy Data Tools: one command for every question, on a folder of a farm's DairyComp and EZfeed exports.

  python dairy.py files              --folder "Farm Exports"            which file is which, and what's missing
  python dairy.py commands           [--folder F] [--years 3]           the DairyComp reports to save (SHOW, never LIST)
  python dairy.py check              "SHOW ID PEN FOR PEN=21" [--folder F]   what would go wrong typing it on this farm
  python dairy.py items              --folder F                         every DairyComp item on the farm, and what it is
  python dairy.py herd               --folder F                         the herd now
  python dairy.py pens               --folder F                         one line per pen
  python dairy.py pen                --folder F --pen 21 [--days 30]    one pen
  python dairy.py cow                --folder F --cow 1100              one cow
  python dairy.py pen-feed           --folder F [--milk-price 21.5] [--days 7] [--pen 21]
  python dairy.py ration-lab         --folder F [--pen 21] [--days 7]   build a Dairy Ration Lab / MCP handoff payload
  python dairy.py loading            --folder F [--by ingredient|pen|feeder] [--days 14]
  python dairy.py refusals           --folder F [--days 7]
  python dairy.py consistency        --folder F [--days 14]
  python dairy.py fresh              --folder F                         fresh cows: diseases, early exits, first tests
  python dairy.py components         --folder F                         fat, protein, fat:protein, MUN
  python dairy.py udder              --folder F                         high SCC, new and chronic, clinical mastitis
  python dairy.py scc-screen         --folder F [--by none|parity|pen] [--fresh-dim 40]
  python dairy.py scc-dynamics       --folder F [--by none|parity]      DHI-302 new, chronic, cured, dry-period dynamics
  python dairy.py mastitis           --folder F [--by none|parity|dim_band|month] [--first-only]
  python dairy.py repro              --folder F [--vwp 50]              21-day pregnancy rate, conception by service
  python dairy.py pregnancy-rate     --folder F [--vwp 50] [--by none|parity|calving_month] [--cycles]
  python dairy.py pregnant-by        --folder F [--by none|parity] [--dim 100,150,200]
  python dairy.py first-service      --folder F [--vwp 50] [--by none|parity]
  python dairy.py inter-service      --folder F [--by none|parity]      inter-service interval distribution (21d return cycles)
  python dairy.py heifer-repro       --folder F [--by none|breeding_month]
  python dairy.py time-to-pregnancy  --folder F [--by none|parity|COL]  Kaplan-Meier days open & log-rank test
  python dairy.py pregnancy-loss     --folder F [--by none|parity] [--followed-days 60]
  python dairy.py calving-interval   --folder F [--by none|parity]
  python dairy.py age-first-calving  --folder F [--by none|calving_year]
  python dairy.py conception         --folder F [--by service|month|dim_band|parity|breeding_code|technician|sire]
  python dairy.py dry-period         --folder F [--by none|parity]
  python dairy.py calving            --folder F [--by none|parity]      dystocia, stillbirth, sex ratio, twins, gestation
  python dairy.py disease-effects    --folder F --event metritis [--within-dim 30] [--removal-dim 60]
  python dairy.py risk-ratio         --folder F --outcome metritis --exposure retained_placenta [--exposed VAL]
  python dairy.py mh-rr              --folder F --outcome metritis --exposure retained_placenta [--strata parity]
  python dairy.py survival           --folder F [--by none|parity] [--horizons 60,150,305]
  python dairy.py lactations         --folder F [--within-dim 21|lactation]
  python dairy.py exits              --folder F                         who left, and when
  python dairy.py left-reasons       --folder F [--by none|parity|dim_band]
  python dairy.py left-herd          --folder F [--by none|parity|calving_month] [--dim 30,60,100,305]
  python dairy.py event-months       --folder F --event metritis [--by none|parity]
  python dairy.py audit              --folder F                         record-quality & completeness audit
  python dairy.py weekly             --folder F [--milk-price 21.5]     all of it, for a visit
  python dairy.py card               --folder F --pen 21 | --cow 3004 | --feed | --weekly [--actions FILE] [--out FILE]
                                     [--slide: bigger and fewer items, for a projector; --pen and --feed]

Add --json FILE to any of them for every figure (cards are drawn from it). Read-only: the folder is never changed and
nothing is sent anywhere. Python 3.10 or later, standard library only.
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True   # leave nothing behind in the skill folder
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dairytools.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
