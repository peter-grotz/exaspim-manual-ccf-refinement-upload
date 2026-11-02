"""Check a manual CCF refinement before it is published.

The refinement is made by hand in 3D Slicer: a displacement field (``.nrrd``) plus the
thin-plate-spline landmark transforms it was composed from (``.h5``). Everything here reads
headers and landmark tables only; the 13 GB field is never loaded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import h5py
import nrrd
import numpy as np

FIELD_NAME = re.compile(r"^(?P<subject>\d+)_manual_displacement_field\.nrrd$")
"""Required field name; the SWC transform applies whatever single ``.nrrd`` it finds."""

TRANSFORM_NAME = re.compile(r"^[Tt]ransform_?(?P<index>\d+)h?\.h5$")
"""Slicer's ``Transform<N>h.h5``, or the ``transform_<N>.h5`` the field generator writes."""

CCF_10UM_SIZE = (1320, 800, 1140)
CCF_10UM_DIRECTIONS = np.array([[0.0, 0.01, 0.0], [0.0, 0.0, -0.01], [-0.01, 0.0, 0.0]])
"""Rows are the voxel axes in LPS mm, as Slicer exports the CCF 10 um grid."""

LPS = "left-posterior-superior"


class ValidationError(ValueError):
    """Raised when the inputs are not a publishable refinement."""


@dataclass(frozen=True)
class Refinement:
    """A validated refinement.

    Attributes
    ----------
    subject : str
        Subject id, from the field's name.
    field : Path
        The displacement field.
    transforms : tuple[Path, ...]
        The landmark transforms, in the order they are applied.
    landmarks : tuple[int, ...]
        Landmark count of each transform.
    """

    subject: str
    field: Path
    transforms: tuple[Path, ...]
    landmarks: tuple[int, ...]


def find_inputs(folder: Path) -> tuple[Path, list[Path]]:
    """Find the one field and the transforms in ``folder``.

    Parameters
    ----------
    folder : Path
        Folder holding the refinement, searched recursively.

    Returns
    -------
    tuple[Path, list[Path]]
        The field, and the transforms sorted by their number.

    Raises
    ------
    ValidationError
        If there is not exactly one forward ``.nrrd``, or no ``.h5``, or a transform name
        has no number or repeats one.
    """
    if not folder.is_dir():
        raise ValidationError(f"Input folder {folder} does not exist")
    # The field generator writes an inverse field beside the forward one; only the
    # forward field is published.
    fields = sorted(p for p in folder.rglob("*.nrrd") if "inverse" not in p.name.lower())
    if len(fields) != 1:
        raise ValidationError(
            f"Expected exactly one forward .nrrd in {folder}, found {len(fields)}: "
            f"{[f.name for f in fields]}"
        )
    transforms = sorted(folder.rglob("*.h5"))
    if not transforms:
        raise ValidationError(f"No .h5 transforms in {folder}")
    numbered = {}
    for path in transforms:
        match = TRANSFORM_NAME.match(path.name)
        if not match:
            raise ValidationError(f"{path.name}: expected Transform<N>h.h5 or transform_<N>.h5")
        index = int(match["index"])
        if index in numbered:
            raise ValidationError(f"{path.name} and {numbered[index].name} share number {index}")
        numbered[index] = path
    return fields[0], [numbered[i] for i in sorted(numbered)]


def check_field(path: Path) -> str:
    """Check the field's name and header, and return the subject it names.

    Parameters
    ----------
    path : Path
        The displacement field.

    Returns
    -------
    str
        The subject id in the file name.

    Raises
    ------
    ValidationError
        If the name is not ``<subject>_manual_displacement_field.nrrd``, or the header is not
        a 3-vector field on the CCF 10 um grid in LPS.
    """
    match = FIELD_NAME.match(path.name)
    if not match:
        raise ValidationError(
            f"{path.name}: the field must be named <subject>_manual_displacement_field.nrrd"
        )
    try:
        header = nrrd.read_header(str(path))
    except Exception as error:  # any unreadable header is the same failure
        raise ValidationError(f"{path.name} is not a readable NRRD: {error}") from error

    sizes = tuple(int(s) for s in header.get("sizes", ()))
    kinds = [str(k) for k in header.get("kinds", [])]
    problems = []
    if int(header.get("dimension", 0)) != 4 or len(sizes) != 4:
        problems.append(f"dimension {header.get('dimension')} (expected 4)")
    elif sizes[0] != 3 or "vector" not in kinds[0]:
        problems.append(f"first axis size {sizes[0]}, kind {kinds[:1]} (expected a 3-vector)")
    elif sizes[1:] != CCF_10UM_SIZE:
        problems.append(f"grid {sizes[1:]} (expected CCF 10 um {CCF_10UM_SIZE})")
    if header.get("space") != LPS:
        problems.append(f"space {header.get('space')!r} (expected {LPS!r})")
    directions = np.asarray(header.get("space directions", []), dtype=float)
    if directions.shape != (4, 3) or not np.allclose(directions[1:], CCF_10UM_DIRECTIONS):
        problems.append("space directions are not the CCF 10 um grid in LPS mm")
    if problems:
        raise ValidationError(f"{path.name}: " + "; ".join(problems))
    return match["subject"]


def check_transform(path: Path) -> int:
    """Check one Slicer landmark transform and return its landmark count.

    Parameters
    ----------
    path : Path
        A ``.h5`` transform.

    Returns
    -------
    int
        Number of landmarks.

    Raises
    ------
    ValidationError
        If it is not a thin-plate spline with matching source and target landmarks.
    """
    try:
        with h5py.File(path, "r") as handle:
            group = handle["TransformGroup/0"]
            kind = group["TransformType"][()][0]
            kind = kind.decode() if isinstance(kind, bytes) else str(kind)
            source = np.asarray(group["TransformParameters"]).size
            target = np.asarray(group["TransformFixedParameters"]).size
    except (OSError, KeyError) as error:
        raise ValidationError(f"{path.name} is not a Slicer transform: {error}") from error
    if "ThinPlateSpline" not in kind:
        raise ValidationError(f"{path.name}: transform type {kind!r} (expected a ThinPlateSpline)")
    if source == 0 or source != target or source % 3:
        raise ValidationError(
            f"{path.name}: {source} source and {target} target values (expected matching 3-D points)"
        )
    return source // 3


def validate(folder: Path) -> Refinement:
    """Find and check everything in ``folder``.

    Parameters
    ----------
    folder : Path
        Folder holding the field and its transforms.

    Returns
    -------
    Refinement
        The validated refinement.
    """
    field, transforms = find_inputs(folder)
    subject = check_field(field)
    landmarks = tuple(check_transform(path) for path in transforms)
    return Refinement(subject, field, tuple(transforms), landmarks)
