"""Field and transform checks."""

import pytest
from conftest import make_refinement, write_field, write_transform
from validate import ValidationError, check_field, check_transform, find_inputs, validate


def test_a_refinement_is_validated_in_applied_order(tmp_path):
    refinement = validate(make_refinement(tmp_path, transforms=(2, 10, 1)))
    assert refinement.subject == "841260"
    assert [t.name for t in refinement.transforms] == [
        "Transform1h.h5",
        "Transform2h.h5",
        "Transform10h.h5",
    ]
    assert refinement.landmarks == (3, 4, 12)


def test_generator_transform_names_are_accepted(tmp_path):
    write_field(tmp_path / "841260_manual_displacement_field.nrrd")
    write_transform(tmp_path / "transform_1.h5")
    assert [t.name for t in find_inputs(tmp_path)[1]] == ["transform_1.h5"]


@pytest.mark.parametrize(
    "names, message",
    [
        (
            [
                "841260_manual_displacement_field.nrrd",
                "841260_manual_inverse_displacement_field.nrrd",
            ],
            "exactly one .nrrd",
        ),
        ([], "exactly one .nrrd"),
    ],
)
def test_anything_but_one_field_is_refused(tmp_path, names, message):
    for name in names:
        write_field(tmp_path / name)
    write_transform(tmp_path / "Transform1h.h5")
    with pytest.raises(ValidationError, match=message):
        find_inputs(tmp_path)


def test_transforms_are_required_numbered_and_unique(tmp_path):
    write_field(tmp_path / "841260_manual_displacement_field.nrrd")
    with pytest.raises(ValidationError, match="No .h5"):
        find_inputs(tmp_path)
    write_transform(tmp_path / "landmarks.h5")
    with pytest.raises(ValidationError, match="expected Transform<N>h.h5"):
        find_inputs(tmp_path)
    (tmp_path / "landmarks.h5").unlink()
    write_transform(tmp_path / "Transform1h.h5")
    write_transform(tmp_path / "transform_1.h5")
    with pytest.raises(ValidationError, match="share number 1"):
        find_inputs(tmp_path)


@pytest.mark.parametrize(
    "name", ["field.nrrd", "841260_manual_inverse_displacement_field.nrrd", "841260_field.nrrd"]
)
def test_the_field_name_is_enforced(tmp_path, name):
    with pytest.raises(ValidationError, match="must be named"):
        check_field(write_field(tmp_path / name))


@pytest.mark.parametrize(
    "header, message",
    [
        ({"sizes": "3 660 400 570"}, "grid"),
        ({"sizes": "1 1320 800 1140"}, "3-vector"),
        ({"kinds": "domain domain domain domain"}, "3-vector"),
        ({"space": "right-anterior-superior"}, "space"),
        ({"directions": "none (0.01,0,0) (0,0.01,0) (0,0,0.01)"}, "space directions"),
        ({"directions": "none (0,10,0) (0,0,-10) (-10,0,0)"}, "space directions"),
    ],
)
def test_a_field_off_the_ccf_10um_lps_grid_is_refused(tmp_path, header, message):
    path = write_field(tmp_path / "841260_manual_displacement_field.nrrd", **header)
    with pytest.raises(ValidationError, match=message):
        check_field(path)


def test_an_unreadable_field_is_refused(tmp_path):
    path = tmp_path / "841260_manual_displacement_field.nrrd"
    path.write_text("not an nrrd")
    with pytest.raises(ValidationError, match="not a readable NRRD"):
        check_field(path)


def test_transform_contents_are_checked(tmp_path):
    assert check_transform(write_transform(tmp_path / "a.h5", landmarks=7)) == 7
    with pytest.raises(ValidationError, match="ThinPlateSpline"):
        check_transform(write_transform(tmp_path / "b.h5", kind="AffineTransform_double_3_3"))
    with pytest.raises(ValidationError, match="matching"):
        check_transform(write_transform(tmp_path / "c.h5", landmarks=4, target=5))
    (tmp_path / "d.h5").write_bytes(b"not hdf5")
    with pytest.raises(ValidationError, match="not a Slicer transform"):
        check_transform(tmp_path / "d.h5")
