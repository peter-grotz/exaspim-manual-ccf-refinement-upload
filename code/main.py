"""Publish a manual CCF refinement to its processed dataset.

1. Validate the field and its transforms (:mod:`validate`).
2. Check the dataset: it has a CCF registration, and its subject is the field's.
3. Write ``processing.json`` (:mod:`metadata`) to ``/results``, and the dataset's root
   ``processing.json`` with the refinement added, if the dataset has one.
4. Upload the field, the transforms and ``processing.json`` to
   ``<dataset>/manual_ccf_refinement/``, refusing to overwrite an existing refinement
   unless ``--replace``, then the updated root ``processing.json``. With ``--dry-run``
   the same files are written to ``/results`` instead.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from validate import ValidationError, validate

from metadata import OUTPUT_DIR, RootRecordError, add_to_root, build_processing, parse_when, to_json

logger = logging.getLogger("upload")

DEFAULT_BUCKET = "aind-open-data"
SUBJECT_FILES = ("subject.json", "data_description.json")
REGISTRATION = "ccf_alignment"
TRANSFORMS_DIR = "transforms"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Folder holding the .nrrd field and the .h5 transforms.",
    )
    parser.add_argument("--dataset", required=True, help="Processed dataset name or s3:// URI.")
    parser.add_argument("--annotator", required=True, help="Full name of the annotator.")
    parser.add_argument("--slicer-version", required=True)
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD or ISO date-time.")
    parser.add_argument("--end-date", default="")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace a refinement already published for the dataset.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
    )
    parser.add_argument("--results-dir", type=Path, default=Path("../results"))
    return parser.parse_args(argv)


def dataset_root(spec: str) -> str:
    """Turn a dataset name or ``s3://`` URI into ``<bucket>/<dataset>``."""
    spec = spec.strip().rstrip("/")
    if spec.startswith("s3://"):
        parsed = urlparse(spec)
        key = parsed.path.lstrip("/")
        if not parsed.netloc or not key:
            raise ValidationError(f"{spec!r} names no dataset")
        return f"{parsed.netloc}/{key.split('/')[0]}"
    if "/" in spec or not spec:
        raise ValidationError(f"{spec!r} is not a dataset name or s3:// URI")
    return f"{DEFAULT_BUCKET}/{spec}"


def dataset_subject(fs, root: str) -> str:
    """Read the dataset's subject from its own metadata."""
    for filename in SUBJECT_FILES:
        try:
            subject = str(json.loads(fs.cat(f"{root}/{filename}")).get("subject_id") or "")
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if subject:
            return subject
    raise ValidationError(f"No subject_id in s3://{root}/{' or '.join(SUBJECT_FILES)}")


def run(args: argparse.Namespace, fs) -> int:
    """Run against ``fs`` (S3 in production). Returns the exit status."""
    refinement = validate(args.input_dir)
    logger.info(
        "Field %s for subject %s; %d transforms (%s landmarks)",
        refinement.field.name,
        refinement.subject,
        len(refinement.transforms),
        list(refinement.landmarks),
    )

    root = dataset_root(args.dataset)
    if not fs.exists(f"{root}/{REGISTRATION}"):
        raise ValidationError(f"s3://{root}/ has no {REGISTRATION}/ registration to refine")
    subject = dataset_subject(fs, root)
    if subject != refinement.subject:
        raise ValidationError(
            f"The field is for subject {refinement.subject}, but s3://{root}/ is subject {subject}"
        )
    target = f"{root}/{OUTPUT_DIR}"
    existing = fs.find(target) if fs.exists(target) else []
    if existing and not args.replace:
        raise ValidationError(
            f"s3://{target}/ already holds {len(existing)} file(s); pass --replace to replace them"
        )

    processing = build_processing(
        args.annotator.strip(),
        args.slicer_version.strip(),
        parse_when(args.start_date),
        parse_when(args.end_date) if args.end_date.strip() else None,
    )
    staged = args.results_dir / OUTPUT_DIR / "processing.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(to_json(processing), encoding="utf-8")
    logger.info("Wrote %s", staged)

    # The dataset's root record gains the refinement; a dataset without one keeps the
    # refinement's record only in its folder.
    root_key = f"{root}/processing.json"
    staged_root = None
    if fs.exists(root_key):
        try:
            current = json.loads(fs.cat(root_key))
        except ValueError as error:
            raise ValidationError(f"s3://{root_key} is not readable JSON: {error}") from error
        try:
            updated = add_to_root(current, processing, args.replace)
        except RootRecordError as error:
            raise ValidationError(f"s3://{root_key}: {error}") from error
        staged_root = args.results_dir / "processing.json"
        staged_root.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        logger.info("Wrote %s (root record with the refinement added)", staged_root)
    else:
        logger.warning("No s3://%s; the refinement is recorded only in its folder", root_key)

    uploads = {str(refinement.field): f"{target}/{refinement.field.name}"}
    uploads |= {str(t): f"{target}/{TRANSFORMS_DIR}/{t.name}" for t in refinement.transforms}
    uploads[str(staged)] = f"{target}/processing.json"
    if args.dry_run:
        # Mirror the upload into /results/manual_ccf_refinement/, so the published tree
        # can be inspected; nothing is written to S3.
        for local, remote in uploads.items():
            mirrored = args.results_dir / OUTPUT_DIR / Path(remote).relative_to(target)
            if mirrored != staged:
                mirrored.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local, mirrored)
            logger.info("Dry run: %s -> s3://%s (copied to %s)", local, remote, mirrored)
        if staged_root:
            logger.info("Dry run: %s -> s3://%s", staged_root, root_key)
        return 0

    # Upload first, then remove what the new refinement did not overwrite, so a failed
    # upload never leaves the dataset with no refinement at all.
    fs.put(list(uploads), list(uploads.values()))
    missing = [remote for remote in uploads.values() if not fs.exists(remote)]
    if missing:
        raise RuntimeError(f"Upload incomplete; missing: {missing}")
    stale = sorted(set(existing) - set(uploads.values()))
    if stale:
        logger.warning("Removing %d file(s) of the replaced refinement: %s", len(stale), stale)
        fs.rm(stale)
    logger.info("Published %d files to s3://%s/", len(uploads), target)
    if staged_root:
        # Last, so the root record never names a refinement that is not there.
        fs.put(str(staged_root), root_key)
        logger.info("Updated s3://%s", root_key)
    return 0


def main() -> int:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    import s3fs

    try:
        return run(args, s3fs.S3FileSystem())
    except ValidationError as error:
        logger.error("%s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
