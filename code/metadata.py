"""The ``processing.json`` published with a manual CCF refinement.

Only what the schema requires, plus ``output_path`` and a one-line note, as AIND asks for
manual steps. The step is not run by a pipeline, so it names none.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone

from aind_data_schema.components.identifiers import Code
from aind_data_schema.core.processing import DataProcess, Processing, ProcessStage
from aind_data_schema_models.process_names import ProcessName

PROCESS_NAME = "Manual CCF refinement"
OUTPUT_DIR = "manual_ccf_refinement"
"""Subfolder of the processed dataset the refinement is published to."""

SLICER_URL = "https://github.com/Slicer/Slicer"
NOTES = "Landmarks placed manually in 3D Slicer; exported as a displacement field."


def parse_when(value: str) -> datetime:
    """Read a date or date-time; one without a timezone is taken as UTC.

    Parameters
    ----------
    value : str
        ``YYYY-MM-DD``, ``YYYY/MM/DD`` or an ISO 8601 date-time.

    Returns
    -------
    datetime
        A timezone-aware date-time.

    Raises
    ------
    ValueError
        If the value is neither.
    """
    value = value.strip().replace("/", "-")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(value), time())
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def build_processing(
    annotator: str, slicer_version: str, start: datetime, end: datetime | None = None
) -> Processing:
    """Describe the manual refinement.

    Parameters
    ----------
    annotator : str
        Full name of whoever placed the landmarks.
    slicer_version : str
        3D Slicer version used.
    start : datetime
        When the annotation started.
    end : datetime | None, optional
        When it finished.

    Returns
    -------
    Processing
        The record, with no dependency on other processes; the link to the registration it
        refines is added when it is merged into the dataset's root ``processing.json``.
    """
    process = DataProcess(
        process_type=ProcessName.IMAGE_ATLAS_ALIGNMENT,
        name=PROCESS_NAME,
        stage=ProcessStage.PROCESSING,
        code=Code(url=SLICER_URL, version=slicer_version),
        experimenters=[annotator],
        start_date_time=start,
        end_date_time=end,
        output_path=OUTPUT_DIR,
        notes=NOTES,
    )
    return Processing(data_processes=[process], dependency_graph={PROCESS_NAME: []})


def to_json(processing: Processing) -> str:
    """Serialise without empty fields."""
    return processing.model_dump_json(indent=2, exclude_none=True)


REGISTRATION_PROCESS = "Image atlas alignment - 10 um"
"""The registration step the refinement corrects; its input in the dependency graph."""


class RootRecordError(ValueError):
    """Raised when the refinement cannot be added to the dataset's root record."""


def add_to_root(root: dict, processing: Processing, replace: bool = False) -> dict:
    """Add the refinement to the dataset's root ``processing.json``.

    Only the refinement's entry and its dependency-graph edge change; every other field is
    kept exactly as read, so readers of the existing record are unaffected.

    Parameters
    ----------
    root : dict
        The dataset's root ``processing.json``, as read.
    processing : Processing
        The refinement's record, from :func:`build_processing`.
    replace : bool, optional
        Replace an existing refinement entry instead of refusing.

    Returns
    -------
    dict
        The updated root record, validated.

    Raises
    ------
    RootRecordError
        If the root already records a refinement and ``replace`` is false, or the result
        does not validate.
    """
    (entry,) = json.loads(to_json(processing))["data_processes"]
    processes = list(root.get("data_processes") or [])
    if any(p.get("name") == PROCESS_NAME for p in processes):
        if not replace:
            raise RootRecordError(f"The root processing.json already has {PROCESS_NAME!r}")
        processes = [p for p in processes if p.get("name") != PROCESS_NAME]
    processes.append(entry)
    updated = {**root, "data_processes": processes}
    if root.get("dependency_graph") is not None:
        names = {p.get("name") for p in processes}
        updated["dependency_graph"] = {
            **root["dependency_graph"],
            PROCESS_NAME: [REGISTRATION_PROCESS] if REGISTRATION_PROCESS in names else [],
        }
    try:
        Processing.model_validate(updated)
    except ValueError as error:
        raise RootRecordError(f"The updated root processing.json is invalid: {error}") from error
    return updated
