"""Dairy Data Tools: read a farm's DairyComp and EZfeed exports and work out what a nutritionist asks.

Python standard library only. Read-only: nothing is written except where a command is told to, and nothing is sent
over the network. Ported from the Rossow Data Lab's R package (Padraig Lucey), with the same rules.

The one source is tools/dairytools in the repository; tools/sync_scripts.py copies it into each skill's scripts/
folder, because in Claude's chat only a skill's own folder reaches the code sandbox.
"""

__version__ = "0.2.0"
