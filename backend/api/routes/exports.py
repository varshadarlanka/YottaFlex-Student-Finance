from __future__ import annotations

import logging
import tempfile
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.api.deps import get_db
from backend.exports.exporter import (
    export_persisted_ground_truth,
    export_table_format,
)

router = APIRouter()
EXPORT_ROOT = Path(__file__).resolve().parents[3] / "exports"
logger = logging.getLogger(__name__)


def _export_tables(
    db_path: str,
    out_dir: Path,
    file_format: str,
) -> Dict[str, Path]:
    try:
        return export_table_format(db_path, out_dir, file_format)
    except Exception as exc:
        logger.exception(
            "Failed to export %s tables from %s to %s",
            file_format,
            db_path,
            out_dir,
        )
        raise HTTPException(
            status_code=500,
            detail=f"{file_format.upper()} export failed; see server log for details",
        ) from exc


@router.get("/export/csv", summary="Export the main tables as CSV")
def export_csv(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
    out_dir = EXPORT_ROOT / "csv"
    paths = _export_tables(db_path, out_dir, "csv")
    return {
        "export_dir": str(out_dir.relative_to(EXPORT_ROOT.parent)),
        "files": [
            str(path.relative_to(EXPORT_ROOT.parent))
            for path in paths.values()
        ],
    }


@router.get("/export/json", summary="Export the main tables as JSON")
def export_json(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
    out_dir = EXPORT_ROOT / "json"
    paths = _export_tables(db_path, out_dir, "json")
    return {
        "export_dir": str(out_dir.relative_to(EXPORT_ROOT.parent)),
        "files": [
            str(path.with_suffix(".json").relative_to(EXPORT_ROOT.parent))
            for path in paths.values()
        ],
    }


def _download_archive(
    conn: sqlite3.Connection,
    file_format: str,
) -> FileResponse:
    db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
    out_dir = EXPORT_ROOT / file_format
    archive_path = None
    try:
        paths = _export_tables(db_path, out_dir, file_format)
        ground_truth = export_persisted_ground_truth(db_path, EXPORT_ROOT)[file_format]

        with tempfile.NamedTemporaryFile(
            prefix=f"yottaflex-{file_format}-",
            suffix=".zip",
            delete=False,
        ) as temporary_archive:
            archive_path = Path(temporary_archive.name)

        with zipfile.ZipFile(
            archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zip_file:
            for path in paths.values():
                zip_file.write(path, arcname=path.name)
            zip_file.write(ground_truth, arcname=ground_truth.name)
    except HTTPException:
        raise
    except Exception as exc:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        logger.exception(
            "Failed to create %s download archive from %s",
            file_format,
            db_path,
        )
        raise HTTPException(
            status_code=500,
            detail=f"{file_format.upper()} download failed; see server log for details",
        ) from exc

    filename = f"yottaflex-{file_format}-export.zip"
    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@router.get("/export/csv/download", summary="Download all CSV exports")
def download_csv(conn: sqlite3.Connection = Depends(get_db)) -> Response:
    return _download_archive(conn, "csv")


@router.get("/export/json/download", summary="Download all JSON exports")
def download_json(conn: sqlite3.Connection = Depends(get_db)) -> Response:
    return _download_archive(conn, "json")
