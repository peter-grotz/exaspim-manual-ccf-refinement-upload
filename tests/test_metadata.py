"""The published processing record."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aind_data_schema.core.processing import Processing

from metadata import RootRecordError, add_to_root, build_processing, parse_when, to_json


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


ROOT = json.loads((Path(__file__).parent / "resources" / "root_processing_853533.json").read_text())


def _record():
    return build_processing("Isha Gosai", "5.6.2", parse_when("2026/01/09"))


def test_the_refinement_is_added_to_the_root_and_nothing_else_changes():
    updated = add_to_root(copy.deepcopy(ROOT), _record())
    assert updated["data_processes"][:-1] == ROOT["data_processes"]
    assert updated["data_processes"][-1]["name"] == "Manual CCF refinement"
    assert updated["dependency_graph"] == {
        **ROOT["dependency_graph"],
        "Manual CCF refinement": ["Image atlas alignment - 10 um"],
    }
    assert {
        k: v for k, v in updated.items() if k not in ("data_processes", "dependency_graph")
    } == {k: v for k, v in ROOT.items() if k not in ("data_processes", "dependency_graph")}
    Processing.model_validate(updated)


def test_an_existing_refinement_in_the_root_needs_replace():
    once = add_to_root(copy.deepcopy(ROOT), _record())
    with pytest.raises(RootRecordError, match="already has"):
        add_to_root(once, _record())
    twice = add_to_root(once, _record(), replace=True)
    assert [p["name"] for p in twice["data_processes"]].count("Manual CCF refinement") == 1


def test_without_the_registration_step_the_refinement_has_no_input():
    root = copy.deepcopy(ROOT)
    root["data_processes"] = [
        p for p in root["data_processes"] if p["name"] == "Inference dispatch"
    ]
    root["dependency_graph"] = {"Inference dispatch": []}
    assert add_to_root(root, _record())["dependency_graph"]["Manual CCF refinement"] == []


def test_a_root_without_a_graph_gets_none():
    root = {k: v for k, v in copy.deepcopy(ROOT).items() if k != "dependency_graph"}
    assert "dependency_graph" not in add_to_root(root, _record())
