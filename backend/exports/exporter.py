from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Dict, List


TABLES = [
    "Students",
    "Programs",
    "Terms",
    "FeeSchedules",
    "FeeScheduleLines",
    "Enrollments",
    "Invoices",
    "InvoiceLines",
    "Scholarships",
    "Eligibility",
    "Payments",
    "PaymentAllocations",
    "Refunds",
    "BalanceSnapshots",
    "AuditEvents",
]


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fetch_table_rows(conn: sqlite3.Connection, table: str) -> List[Dict]:
    rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
    return [dict(r) for r in rows]


def export_table_format(
    db_path: str | Path,
    output_dir: str | Path,
    file_format: str,
) -> Dict[str, Path]:
    """Export each known table in one format to the output directory."""
    if file_format not in {"csv", "json"}:
        raise ValueError(f"Unsupported export format: {file_format}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        paths: Dict[str, Path] = {}
        for table in TABLES:
            cursor = conn.execute(f'SELECT * FROM "{table}" ORDER BY 1')
            rows = cursor.fetchall()
            export_path = out_dir / f"{table}.{file_format}"
            if file_format == "csv":
                fieldnames = [column[0] for column in cursor.description or []]
                with export_path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(dict(row) for row in rows)
            else:
                with export_path.open("w", encoding="utf-8") as fh:
                    json.dump([dict(row) for row in rows], fh, indent=2, sort_keys=True)
            paths[table] = export_path
        return paths
    finally:
        conn.close()


def export_csv_json(db_path: str | Path, output_dir: str | Path) -> Dict[str, Path]:
    """Export each known table to both CSV and JSON files."""
    csv_paths = export_table_format(db_path, output_dir, "csv")
    export_table_format(db_path, output_dir, "json")
    return csv_paths


def export_persisted_ground_truth(
    db_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Path]:
    """Export existing ground-truth labels without injecting or changing data."""
    from backend.anomaly.injector import AnomalyInjector

    injector = AnomalyInjector(db_path)
    records = injector.get_ground_truth()
    expected_types = {
        "PAYMENT_ALLOC_EXCEEDS_PAYMENT",
        "SCHOLARSHIP_EXCEEDS_FEES",
        "DUPLICATE_INVOICE",
        "REFUND_EXCEEDS_NET_PAID",
        "BALANCE_DISAGREES_LEDGER",
    }
    if len(records) != len(expected_types) or {
        record.issue_type for record in records
    } != expected_types:
        raise RuntimeError("Database does not contain all five required anomaly labels")
    return injector.export_ground_truth(output_dir=output_dir)


def write_source_manifest(
    db_path: str | Path,
    output_dir: str | Path,
    seed: int = 20261022,
) -> Path:
    """Write a content-hash manifest for the canonical root export package."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        tables = [
            {
                "name": table,
                "row_count": conn.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0],
            }
            for table in TABLES
        ]
    finally:
        conn.close()

    source_db = Path(db_path)
    artifacts = []
    for path in sorted(out_dir.iterdir()):
        if not path.is_file() or path.name == "source_manifest.json":
            continue
        if path.suffix not in {".csv", ".json", ".sql"}:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        artifacts.append(
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )

    manifest = {
        "seed": seed,
        "database": source_db.name,
        "table_count": len(tables),
        "total_rows": sum(table["row_count"] for table in tables),
        "tables": tables,
        "artifacts": artifacts,
    }
    manifest_path = out_dir / "source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _sql_literal(value) -> str:
    """Convert a Python value to a SQL literal string."""
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"


def export_sql_seed(db_path: str | Path, output_file: str | Path) -> Path:
    """Create a SQL seed dump with actual values that can be re-imported."""
    out = Path(output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        lines: List[str] = ["PRAGMA foreign_keys = OFF;", "BEGIN;"]
        for table in TABLES:
            rows = _fetch_table_rows(conn, table)
            if not rows:
                continue
            columns = list(rows[0].keys())
            col_list = ", ".join(columns)
            for row in rows:
                vals = ", ".join(_sql_literal(row.get(col)) for col in columns)
                lines.append(
                    f"INSERT INTO {table} ({col_list}) VALUES ({vals});"
                )
        lines.append("COMMIT;")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
    finally:
        conn.close()


def export_ground_truth(
    db_path: str | Path,
    output_dir: str | Path,
    seed: int = 20261022,
) -> Dict[str, Path]:
    """Run anomaly injection on a temporary copy and export ground truth."""
    import shutil
    import tempfile
    from backend.anomaly.injector import AnomalyInjector

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.mkdtemp()
    tmp_db = Path(tmp) / "gt_export.db"
    shutil.copy2(str(db_path), str(tmp_db))

    try:
        injector = AnomalyInjector(tmp_db, seed=seed)
        injector.inject_all()
        return injector.export_ground_truth(out_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def export_all_tables(db_path: str | Path, output_dir: str | Path) -> Dict[str, Dict[str, Path]]:
    csv_paths = export_csv_json(db_path, output_dir)
    sql_path = export_sql_seed(db_path, Path(output_dir) / "seed.sql")
    gt_paths = export_ground_truth(db_path, output_dir)
    manifest_path = write_source_manifest(db_path, output_dir)
    return {
        "csv": csv_paths,
        "sql": {"seed": sql_path},
        "ground_truth": gt_paths,
        "manifest": {"source": manifest_path},
    }
