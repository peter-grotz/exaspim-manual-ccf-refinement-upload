"""The published processing record."""

import json
from datetime import datetime, timezone

from aind_data_schema.core.processing import Processing

from metadata import build_processing, parse_when, to_json


def test_the_record_is_minimal_and_valid():
    record = json.loads(to_json(build_processing("Jane Doe", "5.6.2", parse_when("2026-08-03"))))
    Processing.model_validate(record)
    (process,) = record["data_processes"]
    assert process["name"] == "Manual CCF refinement"
    assert process["process_type"] == "Image atlas alignment"
    assert process["output_path"] == "manual_ccf_refinement"
    assert process["code"] == {
        "object_type": "Code",
        "url": "https://github.com/Slicer/Slicer",
        "version": "5.6.2",
    }
    assert process["experimenters"] == ["Jane Doe"]
    assert "pipeline_name" not in process and "end_date_time" not in process
    assert record["dependency_graph"] == {"Manual CCF refinement": []}


def test_an_end_date_is_recorded_when_given():
    record = build_processing(
        "Jane Doe", "5.6.2", parse_when("2026-08-03"), parse_when("2026-08-07")
    )
    assert record.data_processes[0].end_date_time == datetime(2026, 8, 7, tzinfo=timezone.utc)


def test_dates_without_a_timezone_are_utc():
    assert parse_when("2026-08-03") == datetime(2026, 8, 3, tzinfo=timezone.utc)
    assert parse_when("2026/01/09") == datetime(2026, 1, 9, tzinfo=timezone.utc)
    assert parse_when("2026-08-03T09:30:00") == datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)
    assert parse_when("2026-08-03T09:30:00-07:00").utcoffset().total_seconds() == -7 * 3600
