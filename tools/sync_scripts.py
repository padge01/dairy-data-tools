"""Copy the shared code into each skill (in Claude's chat only a skill's own folder reaches the code sandbox), and
write the repository's README from the plugin's.

- tools/dairy.py and tools/dairytools/ go into every skill that runs them (DAIRY_SKILLS).
- tools/dairyread.py, ration_change.py and pen_milk.py go into ration-change.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "dairy-data-tools"
DAIRY_SKILLS = ["dairycomp-exports", "ezfeed-exports", "herd-explorer", "pen-feed", "weekly-review"]
DAIRYREAD_SKILLS = ["ration-change"]

for name in DAIRY_SKILLS:
    scripts = PLUGIN / "skills" / name / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "tools" / "dairy.py", scripts / "dairy.py")
    target = scripts / "dairytools"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ROOT / "tools" / "dairytools", target, ignore=shutil.ignore_patterns("__pycache__"))
    print("copied dairy.py and dairytools to", scripts.relative_to(ROOT))
for name in DAIRYREAD_SKILLS:
    scripts = PLUGIN / "skills" / name / "scripts"
    for script in ("dairyread.py", "ration_change.py", "pen_milk.py"):
        shutil.copyfile(ROOT / "tools" / script, scripts / script)
    print("copied dairyread.py, ration_change.py and pen_milk.py to", scripts.relative_to(ROOT))

# The repository's README is the plugin's, plus how the repository is laid out.
DEVELOPERS = """
## Working on it

- `plugins/dairy-data-tools/`: the plugin people install (skills, sample herd, README, licences).
- `tools/dairy.py`, `tools/dairytools/` and the ration-change scripts in `tools/`: the one copy of the code;
  `python tools/sync_scripts.py` copies it into each skill and writes this README. `pyproject.toml` builds the same
  code as the `dairy-data-tools` package on PyPI.
- `tools/make_sample_herd.py`: writes the sample herd (fixed seeds, same files every run).
- `tests/`: `python -m pytest -q tests` (made-up files with known answers, the sample herd, the directory's file limits).
"""
readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
# Pictures by their path in the repository there, so they show on GitHub and in any viewer of the checked-out files.
readme = readme.replace("https://raw.githubusercontent.com/padge01/dairy-data-tools/main/", "")
(ROOT / "README.md").write_text(readme.rstrip("\n") + "\n" + DEVELOPERS, encoding="utf-8", newline="\n")
print("wrote README.md")
