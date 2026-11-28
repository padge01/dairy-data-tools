"""Dairy Data Tools: read a farm's DairyComp and EZfeed exports and work out what a nutritionist or vet asks.

Python 3.10+ standard library only (`dependencies = []`). Read-only: nothing is written except where a command is told
to, and nothing is sent over the network. Ported from the author's earlier R version, with parity verified against R,
plus record-only extensions and a zero-network handoff to Dairy Ration Lab (`lab.dairydatascience.com`).

The one source is `tools/dairytools` in the repository; `tools/sync_scripts.py` copies it into each skill's `scripts/`
folder, because in Claude's chat only a skill's own folder reaches the code sandbox.
"""

from __future__ import annotations

from . import commands, ecosystem, epi, explorer, feeding, herd, io, models, repro, stats, udder, weekly
from .ecosystem import ECOSYSTEM, ration_lab_handoff
from .epi import (
    audit_records,
    calving_outcomes,
    calving_period,
    compare_groups,
    dry_band,
    dry_period_length,
    dry_periods,
    event_months,
    fresh_disease_effects,
    herd_survival,
    lactation_data,
    left_herd,
    left_reasons,
    mantel_haenszel_rr,
    risk_ratio,
)
from .errors import DairyToolsError, FolderNotFoundError, MissingDataError, NotFoundError
from .herd import Herd, load
from .models import Cow, Event, Lactation, to_pandas, to_polars
from .repro import (
    age_first_calving,
    calving_interval,
    conception_by,
    first_service,
    heifer_repro,
    inter_service_intervals,
    pregnancy_loss,
    pregnancy_rate,
    pregnant_by,
    time_to_pregnancy,
)
from .udder import mastitis_incidence, scc_dynamics, scc_screen

__version__ = "0.2.5"

__all__ = [
    "__version__",
    "Cow",
    "DairyToolsError",
    "ECOSYSTEM",
    "Event",
    "FolderNotFoundError",
    "Herd",
    "Lactation",
    "MissingDataError",
    "NotFoundError",
    "age_first_calving",
    "audit_records",
    "calving_interval",
    "calving_outcomes",
    "calving_period",
    "commands",
    "compare_groups",
    "conception_by",
    "dry_band",
    "dry_period_length",
    "dry_periods",
    "ecosystem",
    "epi",
    "event_months",
    "explorer",
    "feeding",
    "first_service",
    "fresh_disease_effects",
    "heifer_repro",
    "herd",
    "herd_survival",
    "inter_service_intervals",
    "io",
    "lactation_data",
    "left_herd",
    "left_reasons",
    "load",
    "mantel_haenszel_rr",
    "mastitis_incidence",
    "models",
    "pregnancy_loss",
    "pregnancy_rate",
    "pregnant_by",
    "ration_lab_handoff",
    "repro",
    "risk_ratio",
    "scc_dynamics",
    "scc_screen",
    "stats",
    "time_to_pregnancy",
    "to_pandas",
    "to_polars",
    "udder",
    "weekly",
]
