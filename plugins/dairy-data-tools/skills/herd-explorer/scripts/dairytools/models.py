"""Lightweight typed records (`@dataclass(slots=True, eq=False)`) with mapping compatibility and optional DataFrame export.

Records use true `__slots__` (rejecting accidental attribute typos), are hashable, expose typed attributes
(`cow.test_milk`, `event.std_event`, `lact.conception_date`), and implement mapping accessors (`row["field"]`,
`row.get("field")`, `"field" in row`, `row.to_dict()`). Farm-specific extra columns live in `.extra`.

Safety boundary:
- `Event.to_dict()` excludes untrusted free-text columns (`remark`, `protocol`, `technician`) by default unless
  `include_untrusted=True` is passed.
- `Cow.to_dict()` excludes unknown free-text string columns in `.extra` by default unless `include_untrusted=True`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any, ClassVar

from . import reference


class _RecordMixin:
    """Mapping-compatible mixin for `@dataclass(slots=True, eq=False)` domain records."""

    __slots__ = ()
    _FIELD_NAMES: ClassVar[tuple[str, ...]] = ()
    _FIELD_SET: ClassVar[frozenset[str]] = frozenset()
    _UNTRUSTED_FIELDS: ClassVar[frozenset[str]] = frozenset()
    extra: dict[str, Any]

    @classmethod
    def _init_field_cache(cls) -> None:
        names = tuple(f.name for f in fields(cls) if f.name != "extra")
        cls._FIELD_NAMES = names
        cls._FIELD_SET = frozenset(names)

    def __getitem__(self, key: str) -> Any:
        if key in self._FIELD_SET:
            return getattr(self, key)
        if key in self.extra:
            return self.extra[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self._FIELD_SET:
            setattr(self, key, value)
        else:
            self.extra[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._FIELD_SET:
            return getattr(self, key)
        return self.extra.get(key, default)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self._FIELD_SET or key in self.extra

    def keys(self) -> list[str]:
        return list(self._FIELD_NAMES) + list(self.extra.keys())

    def __iter__(self) -> Iterator[str]:
        yield from self._FIELD_NAMES
        yield from self.extra.keys()

    def values(self) -> list[Any]:
        return [getattr(self, k) for k in self._FIELD_NAMES] + list(self.extra.values())

    def items(self) -> list[tuple[str, Any]]:
        return [(k, getattr(self, k)) for k in self._FIELD_NAMES] + list(self.extra.items())

    def to_dict(
        self,
        *,
        exclude: frozenset[str] | set[str] | tuple[str, ...] = (),
        include_untrusted: bool = False,
    ) -> dict[str, Any]:
        """Plain dict representation (typed fields plus safe extra columns)."""
        skip = set(exclude)
        if not include_untrusted and self._UNTRUSTED_FIELDS:
            skip.update(self._UNTRUSTED_FIELDS)
        out = {k: getattr(self, k) for k in self._FIELD_NAMES if k not in skip}
        for k, v in self.extra.items():
            if k in skip:
                continue
            if not include_untrusted and isinstance(v, str):
                continue  # free-text unknown farm column
            out[k] = v
        return out

    @classmethod
    def from_mapping(cls, data: dict[str, Any]):
        """Construct a typed record from a standardised dict, placing unknown columns in `.extra`."""
        known: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for k, v in data.items():
            if k in cls._FIELD_SET:
                known[k] = v
            else:
                extra[k] = v
        return cls(**known, extra=extra)


@dataclass(slots=True, eq=False)
class Cow(_RecordMixin):
    """One animal from the cow report(s)."""

    cow_id: str
    animal_id: str = ""
    eid: str | None = None
    official_id: str | None = None
    breed: str | None = None
    birth_date: date | None = None
    pen: str = "No pen"
    previous_pen: str | None = None
    lactation: int | None = None
    fresh_date: date | None = None
    prev_fresh_date: date | None = None
    dry_date: date | None = None
    conception_date: date | None = None
    heat_date: date | None = None
    archive_date: date | None = None
    times_bred: int | None = None
    repro_status: str | None = None
    repro_code: int | None = None
    sire: str | None = None
    last_service_sire: str | None = None
    sire_of_conception: str | None = None
    calf_sex: str | None = None
    fetal_sex: str | None = None
    calving_ease: int | None = None
    test_date: date | None = None
    test_pen: str | None = None
    test_milk: float | None = None
    prev_test_milk: float | None = None
    daily_milk: float | None = None
    test_fat_pct: float | None = None
    test_protein_pct: float | None = None
    test_scc: float | None = None
    prev_test_scc: float | None = None
    test_mun: float | None = None
    first_test_scc: float | None = None
    first_test_dim: int | None = None
    first_test_fat_pct: float | None = None
    first_test_protein_pct: float | None = None
    first_test_milk: float | None = None
    dc_days_in_milk: int | None = None
    dc_linear_score: float | None = None
    dc_prev_linear_score: float | None = None
    dc_first_linear_score: float | None = None
    dc_dry_off_linear_score: float | None = None
    dc_max_linear_score: float | None = None
    left_date: date | None = None
    left_reason: str | None = None
    is_dry: bool = False
    days_in_milk: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, eq=False)
class Event(_RecordMixin):
    """One event from the DairyComp EVENTS export."""

    _UNTRUSTED_FIELDS: ClassVar[frozenset[str]] = frozenset(reference.UNTRUSTED_EVENT_COLUMNS)

    cow_id: str
    event_date: date
    dc_event: str
    animal_id: str = ""
    birth_date: date | None = None
    lactation: int | None = None
    dim_at_event: int | None = None
    std_event: str | None = None
    category: str | None = None
    mapped_by: str | None = None
    remark: str | None = None
    result_code: str | None = None
    technician_code: str | None = None
    breeding_code: str | None = None
    protocol: str | None = None
    technician: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, eq=False)
class Lactation(_RecordMixin):
    """One animal-lactation built from calvings, dry-offs, breedings, pregnancy checks, and exits."""

    animal_id: str
    cow_id: str
    lactation: int | None
    fresh_date: date
    end_date: date | None = None
    end_reason: str = "in milk at export"
    first_service_date: date | None = None
    first_service_dim: int | None = None
    services: int = 0
    conception_date: date | None = None
    days_open: int | None = None
    health_events: int = 0
    fully_observed: bool = False
    start_source: str = "event"
    extra: dict[str, Any] = field(default_factory=dict)


for _cls in (Cow, Event, Lactation):
    _cls._init_field_cache()


def records_to_dicts(
    rows: Sequence[Any],
    *,
    exclude: tuple[str, ...] = (),
    include_untrusted: bool = False,
    json_safe: bool = False,
) -> list[dict[str, Any]]:
    """Convert a sequence of typed records or dicts into plain rectangular dicts.

    Untrusted free-text fields (`remark`, `protocol`, `technician` on `Event`, and unknown string extras on `Cow`)
    are omitted unless `include_untrusted=True`. Set `json_safe=True` to convert `date` values to ISO strings.
    """
    skip = set(exclude)
    if not include_untrusted:
        # Drop any unknown extra column that holds string text on any row (free-text farm column).
        for r in rows:
            if isinstance(r, _RecordMixin):
                for k, v in r.extra.items():
                    if isinstance(v, str):
                        skip.add(k)
    dicts = [
        r.to_dict(exclude=skip, include_untrusted=include_untrusted)
        if isinstance(r, _RecordMixin)
        else {k: v for k, v in r.items() if k not in skip}
        for r in rows
    ]
    if not dicts:
        return []
    all_keys: list[str] = list(dict.fromkeys(k for d in dicts for k in d))
    if json_safe:
        return [{k: (v.isoformat() if isinstance(v, date) else v) for k in all_keys for v in (d.get(k),)} for d in dicts]
    return [{k: d.get(k) for k in all_keys} for d in dicts]


def to_pandas(rows: Sequence[Any], *, exclude: tuple[str, ...] = (), include_untrusted: bool = False):
    """Convert records to a `pandas.DataFrame` using a lazy optional import."""
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("to_pandas() requires the optional pandas package to be installed.") from exc
    return pd.DataFrame.from_records(records_to_dicts(rows, exclude=exclude, include_untrusted=include_untrusted))


def to_polars(rows: Sequence[Any], *, exclude: tuple[str, ...] = (), include_untrusted: bool = False):
    """Convert records to a `polars.DataFrame` using a lazy optional import."""
    try:
        import polars as pl  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("to_polars() requires the optional polars package to be installed.") from exc
    return pl.DataFrame(records_to_dicts(rows, exclude=exclude, include_untrusted=include_untrusted))
