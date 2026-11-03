"""Fixtures: a stand-in for S3, and refinements written as Slicer writes them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
from fsspec.implementations.dirfs import DirFileSystem
from fsspec.implementations.local import LocalFileSystem

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

BUCKET = "aind-open-data"
DATASET = "exaSPIM_841260_2026-07-07_15-13-51_processed_2026-07-26_09-25-11"
CCF_DIRECTIONS = "none (0,0.01,0) (0,0,-0.01) (-0.01,0,0)"


@pytest.fixture
def s3(tmp_path):
    """A filesystem rooted in a temporary directory, addressed like s3fs: ``bucket/key``.

    ``auto_mkdir`` mirrors S3, where writing a key needs no parent "directory".
    """
    root = tmp_path / "s3"
    root.mkdir()
    return DirFileSystem(path=str(root), fs=LocalFileSystem(auto_mkdir=True))


def write_field(
    path: Path,
    sizes="3 1320 800 1140",
    directions=CCF_DIRECTIONS,
    space="left-posterior-superior",
    kinds="vector domain domain domain",
) -> Path:
    """Write a field header as Slicer exports it. Only the header is ever read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "NRRD0004\ntype: float\ndimension: 4\n"
        f"space: {space}\nsizes: {sizes}\nspace directions: {directions}\n"
        f"kinds: {kinds}\nendian: little\nencoding: gzip\nspace origin: (0,0,0)\n\n"
    )
    path.write_bytes(header.encode("ascii") + b"\x1f\x8b not read")
    return path


def write_transform(
    path: Path, landmarks=4, kind="InverseThinPlateSplineKernelTransform_double_3_3", target=None
) -> Path:
    """Write a Slicer landmark transform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        group = handle.create_group("TransformGroup/0")
        group["TransformType"] = np.array([kind.encode()])
        group["TransformParameters"] = np.zeros(landmarks * 3)
        group["TransformFixedParameters"] = np.zeros((landmarks if target is None else target) * 3)
    return path


def make_refinement(folder: Path, subject="841260", transforms=(2, 10, 1)) -> Path:
    """A refinement folder: the field and its numbered transforms."""
    write_field(folder / f"{subject}_manual_displacement_field.nrrd")
    for number in transforms:
        write_transform(folder / f"Transform{number}h.h5", landmarks=number + 2)
    return folder


def make_dataset(fs, subject="841260", registered=True, name=DATASET, root_record=None) -> str:
    """A processed dataset with its subject and, optionally, its CCF registration."""
    root = f"{BUCKET}/{name}"
    fs.pipe(f"{root}/subject.json", json.dumps({"subject_id": subject}).encode())
    if registered:
        fs.pipe(f"{root}/ccf_alignment/processing.json", b"{}")
    if root_record is not None:
        fs.pipe(f"{root}/processing.json", json.dumps(root_record).encode())
    return root
