"""The ``processing.json`` published with a manual CCF refinement.

Only what the schema requires, plus ``output_path`` and a one-line note, as AIND asks for
manual steps. The step is not run by a pipeline, so it names none.
"""

from __future__ import annotations

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
        ``YYYY-MM-DD`` or an ISO 8601 date-time.

    Returns
    -------
    datetime
        A timezone-aware date-time.

    Raises
    ------
    ValueError
        If the value is neither.
    """
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(value.strip()), time())
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
