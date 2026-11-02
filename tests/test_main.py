"""The capsule end to end, against a local stand-in for S3."""

import json
import subprocess
from pathlib import Path

import main
import pytest
from conftest import BUCKET, DATASET, make_dataset, make_refinement, write_field
from validate import ValidationError

TARGET = f"{BUCKET}/{DATASET}/manual_ccf_refinement"


def _args(tmp_path, *extra, dataset=DATASET):
    return main.parse_args(
        [
            "--input-dir",
            str(tmp_path / "in"),
            "--dataset",
            dataset,
            "--annotator",
            "Jane Doe",
            "--slicer-version",
            "5.6.2",
            "--start-date",
            "2026-08-03",
            "--results-dir",
            str(tmp_path / "results"),
            *extra,
        ]
    )


def test_a_dry_run_writes_only_to_results(s3, tmp_path):
    root = make_dataset(s3)
    make_refinement(tmp_path / "in")
    before = sorted(s3.find(root))
    assert main.run(_args(tmp_path, "--dry-run"), s3) == 0
    assert sorted(s3.find(root)) == before
    assert (tmp_path / "results/manual_ccf_refinement/processing.json").is_file()


@pytest.mark.parametrize("dataset", [DATASET, f"s3://{BUCKET}/{DATASET}/ccf_alignment/"])
def test_a_run_publishes_the_field_transforms_and_record(s3, tmp_path, dataset):
    make_dataset(s3)
    make_refinement(tmp_path / "in", transforms=(1, 2))
    assert main.run(_args(tmp_path, dataset=dataset), s3) == 0
    assert sorted(Path(p).relative_to(TARGET).as_posix() for p in s3.find(TARGET)) == [
        "841260_manual_displacement_field.nrrd",
        "processing.json",
        "transforms/Transform1h.h5",
        "transforms/Transform2h.h5",
    ]
    record = json.loads(s3.cat(f"{TARGET}/processing.json"))
    assert record["data_processes"][0]["output_path"] == "manual_ccf_refinement"


@pytest.mark.parametrize(
    "dataset_kwargs, message",
    [({"subject": "823507"}, "is subject 823507"), ({"registered": False}, "no ccf_alignment")],
)
def test_the_wrong_dataset_publishes_nothing(s3, tmp_path, dataset_kwargs, message):
    root = make_dataset(s3, **dataset_kwargs)
    make_refinement(tmp_path / "in")
    before = sorted(s3.find(root))
    with pytest.raises(ValidationError, match=message):
        main.run(_args(tmp_path), s3)
    assert sorted(s3.find(root)) == before


def test_an_existing_refinement_is_kept_unless_replaced(s3, tmp_path):
    make_dataset(s3)
    s3.pipe(f"{TARGET}/old_field.nrrd", b"old")
    s3.pipe(f"{TARGET}/transforms/Transform1h.h5", b"old")
    make_refinement(tmp_path / "in", transforms=(1, 2))
    with pytest.raises(ValidationError, match="--replace"):
        main.run(_args(tmp_path), s3)
    assert s3.cat(f"{TARGET}/old_field.nrrd") == b"old"

    assert main.run(_args(tmp_path, "--replace"), s3) == 0
    assert not s3.exists(f"{TARGET}/old_field.nrrd")
    assert s3.cat(f"{TARGET}/transforms/Transform1h.h5") != b"old"
    nrrds = [p for p in s3.find(TARGET) if p.endswith(".nrrd")]
    assert [Path(p).name for p in nrrds] == ["841260_manual_displacement_field.nrrd"]


@pytest.mark.parametrize("spec", ["", "a/b", "s3://bucket-only"])
def test_a_bad_dataset_spec_is_refused(spec):
    with pytest.raises(ValidationError):
        main.dataset_root(spec)


def test_an_invalid_field_publishes_nothing(s3, tmp_path):
    root = make_dataset(s3)
    make_refinement(tmp_path / "in")
    write_field(tmp_path / "in/841260_manual_displacement_field.nrrd", sizes="3 660 400 570")
    before = sorted(s3.find(root))
    with pytest.raises(ValidationError, match="grid"):
        main.run(_args(tmp_path), s3)
    assert sorted(s3.find(root)) == before


def test_the_run_script_maps_app_panel_slots(tmp_path):
    script = (Path(main.__file__).parent / "run").read_text()
    script = (
        script.replace("pip list > /results/pip_list.txt", ":")
        .replace('python -u main.py "$@"', 'printf "%s|" "$@"')
        .replace("set -ex", "set -e")
    )

    def call(*slots):
        return subprocess.run(
            ["bash", "-c", script, "run", *slots], capture_output=True, text=True, check=True
        ).stdout

    assert call("/data/in", "ds", "Jane Doe", "5.6.2", "2026-08-03", "", "") == (
        "--input-dir|/data/in|--dataset|ds|--annotator|Jane Doe|--slicer-version|5.6.2|"
        "--start-date|2026-08-03|"
    )
    assert call("/data/in", "ds", "J", "5", "2026-08-03", "2026-08-07", "true").endswith(
        "--end-date|2026-08-07|--replace|"
    )
    assert call("/data/in", "ds", "J", "5", "2026-08-03", "", "false", "true").endswith(
        "--start-date|2026-08-03|--dry-run|"
    )
    assert call("--input-dir", "/x") == "--input-dir|/x|"
