# exaspim-manual-ccf-refinement-upload

Publishes a manual CCF refinement made in 3D Slicer to its processed exaSPIM dataset:
validates the files, writes their `processing.json`, and uploads everything to
`<dataset>/manual_ccf_refinement/`, where the SWC transform applies the field.

The field is made outside this capsule; nothing here computes or changes it.

## Inputs (App Panel, in this order)

| # | Parameter | Example | Required |
|---|---|---|---|
| 1 | `input_dir` | `/data/841260_manual_refinement` — a folder with the field and its transforms | yes |
| 2 | `dataset` | `exaSPIM_841260_2026-07-07_15-13-51_processed_2026-07-26_09-25-11` or its `s3://` URI | yes |
| 3 | `annotator` | `Jane Doe` | yes |
| 4 | `slicer_version` | `5.6.2` (Slicer: Help → About) | yes |
| 5 | `start_date` | `2026-08-03` (no timezone means UTC) | yes |
| 6 | `end_date` | `2026-08-07` | no |
| 7 | `replace` | `true` to replace a refinement already published for the dataset | no |

`DRY_RUN=1` (or `--dry-run`) validates and writes `processing.json` to `/results` without
touching S3. AWS credentials need read and write on the dataset.

## Checks — any failure stops the run before anything is written

- **Exactly one `.nrrd`**, named `<subject>_manual_displacement_field.nrrd`: the SWC
  transform applies whatever single `.nrrd` it finds, and refuses two. Inverse fields are
  not published.
- **The field's header**: a 3-vector field on the CCF 10 µm grid (1320 × 800 × 1140,
  10 µm), in LPS millimetres, as Slicer exports it. Only the header is read.
- **The transforms**: at least one; each `Transform<N>h.h5` (Slicer) or `transform_<N>.h5`,
  numbered uniquely, and each a thin-plate spline with matching source and target landmarks.
  They are applied, and listed, in ascending number.
- **The dataset**: it has a `ccf_alignment/` registration to refine, and its subject (from
  its `subject.json` or `data_description.json`) is the one in the field's name.
- **No overwrite**: an existing refinement is replaced only with `replace`. The new files
  are uploaded first, and the old ones removed after, so a failed upload never leaves the
  dataset without one.

## Output — `<dataset>/manual_ccf_refinement/`

```
<subject>_manual_displacement_field.nrrd
transforms/Transform1h.h5 … TransformNh.h5
processing.json
```

`processing.json` describes one process, *Manual CCF refinement*: process type
`Image atlas alignment`, 3D Slicer and its version, the annotator, the dates,
`output_path: manual_ccf_refinement`, and a one-line note. It names no pipeline: the step is
done by hand, not by `exaspim-data-processing`. The link to the registration it refines is
added when it is merged into the dataset's root `processing.json`.

## Tests

```bash
pip install aind-data-schema==2.9.2 pynrrd h5py s3fs pytest
python -m pytest
```

They run the capsule end to end against a local stand-in for S3, with fields and
transforms written as Slicer writes them.
