"""Dairy Data Tools: one command for every question, on a folder of a farm's DairyComp and EZfeed exports.

  python dairy.py files     --folder "Farm Exports"            which file is which, and what's missing
  python dairy.py commands  [--folder F] [--years 3]           the DairyComp reports to save (SHOW, never LIST)
  python dairy.py check     "SHOW ID PEN FOR PEN=21" [--folder F]   what would go wrong typing it on this farm
  python dairy.py items     --folder F                         every DairyComp item on the farm, and what it is
  python dairy.py herd      --folder F                         the herd now
  python dairy.py pens      --folder F                         one line per pen
  python dairy.py pen       --folder F --pen 21 [--days 30]    one pen
  python dairy.py cow       --folder F --cow 1100              one cow
  python dairy.py pen-feed  --folder F [--milk-price 21.5] [--days 7] [--pen 21]
  python dairy.py loading   --folder F [--by ingredient|pen|feeder] [--days 14]
  python dairy.py refusals  --folder F [--days 7]
  python dairy.py consistency --folder F [--days 14]
  python dairy.py fresh     --folder F                         fresh cows: diseases, early exits, first tests
  python dairy.py components --folder F                        fat, protein, fat:protein, MUN
  python dairy.py udder     --folder F                         high SCC, new and chronic, clinical mastitis
  python dairy.py repro     --folder F [--vwp 50]              21-day pregnancy rate, conception by service
  python dairy.py exits     --folder F                         who left, and when
  python dairy.py weekly    --folder F [--milk-price 21.5]     all of it, for a visit
  python dairy.py card      --folder F --pen 21 | --cow 3004 | --feed | --weekly [--actions FILE] [--out FILE]

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
