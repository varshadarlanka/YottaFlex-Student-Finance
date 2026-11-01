import csv
import io
import json
import sqlite3
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api import deps
from backend.api.routes import dashboard as dashboard_routes
from backend.api.routes import exports as export_routes
from backend.api.routes import global_views as global_views_routes
from backend.database.db_manager import DatabaseManager
from backend.exports.exporter import (
    TABLES,
    export_csv_json,
    export_ground_truth,
    export_persisted_ground_truth,
    write_source_manifest,
)


def _client_for_database(db_path: Path) -> TestClient:
    app = FastAPI()
    app.include_router(export_routes.router, prefix="/api/v1")
    app.include_router(dashboard_routes.router, prefix="/api/v1")
    app.include_router(global_views_routes.router, prefix="/api/v1")

    def override_get_db():
        conn = sqlite3.connect(db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    return TestClient(app)


def test_api_database_dependency_supports_thread_handoff_without_reinitializing(
    tmp_path: Path, monkeypatch
):
    db_path = tmp_path / "request.db"
    DatabaseManager(db_path).initialise()
    monkeypatch.setattr(deps, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(
        DatabaseManager,
        "initialise",
        lambda self: pytest.fail("API request reapplied the database schema"),
    )

    connection_generator = deps.get_db()
    opened = threading.Event()
    release = threading.Event()

    def open_connection():
        conn = next(connection_generator)
        assert conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0] == 0
        opened.set()
        assert release.wait(timeout=10)
        return conn, threading.get_ident()

    def close_connection():
        assert opened.wait(timeout=10)
        try:
            next(connection_generator)
        except StopIteration:
            pass
        finally:
            release.set()
        return threading.get_ident()

    with ThreadPoolExecutor(max_workers=2) as pool:
        opened_future = pool.submit(open_connection)
        assert opened.wait(timeout=10)
        close_thread_id = pool.submit(close_connection).result(timeout=10)
        conn, open_thread_id = opened_future.result(timeout=10)

    assert open_thread_id != close_thread_id
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT 1")


def test_empty_table_exports_have_csv_headers(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    DatabaseManager(db_path).initialise()
    output_dir = tmp_path / "exports"

    paths = export_csv_json(db_path, output_dir)

    assert set(paths) == set(TABLES)
    for table in TABLES:
        with (output_dir / f"{table}.csv").open(
            encoding="utf-8", newline=""
        ) as file:
            reader = csv.reader(file)
            assert next(reader)
            assert list(reader) == []
        assert json.loads(
            (output_dir / f"{table}.json").read_text(encoding="utf-8")
        ) == []


def test_source_manifest_records_counts_and_export_hashes(tmp_path: Path):
    db_path = tmp_path / "manifest.db"
    DatabaseManager(db_path).initialise()
    export_csv_json(db_path, tmp_path / "exports")

    manifest_path = write_source_manifest(db_path, tmp_path / "exports")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["seed"] == 20261022
    assert manifest["table_count"] == len(TABLES)
    assert manifest["total_rows"] == 0
    assert len(manifest["tables"]) == len(TABLES)
    assert len(manifest["artifacts"]) == 2 * len(TABLES)
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])


def test_export_endpoints_report_the_correct_formats(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "empty.db"
    DatabaseManager(db_path).initialise()
    export_root = tmp_path / "exports"
    monkeypatch.setattr(export_routes, "EXPORT_ROOT", export_root)

    with _client_for_database(db_path) as client:
        csv_response = client.get("/api/v1/export/csv")
        json_response = client.get("/api/v1/export/json")

    assert csv_response.status_code == 200
    assert json_response.status_code == 200
    assert all(path.endswith(".csv") for path in csv_response.json()["files"])
    assert all(path.endswith(".json") for path in json_response.json()["files"])
    assert not list((export_root / "csv").glob("*.json"))
    assert not list((export_root / "json").glob("*.csv"))
    for path in csv_response.json()["files"] + json_response.json()["files"]:
        assert (tmp_path / path).is_file()


def test_documented_dashboard_summary_route_is_available(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    DatabaseManager(db_path).initialise()

    with _client_for_database(db_path) as client:
        response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["students"] == 0
    assert response.json()["outstanding_paise"] == 0


def test_data_counts_endpoint_reports_all_tables(tmp_path: Path):
    db_path = tmp_path / "empty-counts.db"
    DatabaseManager(db_path).initialise()

    with _client_for_database(db_path) as client:
        response = client.get("/api/v1/data-counts")

    assert response.status_code == 200
    result = response.json()
    assert result["table_count"] == len(TABLES)
    assert result["total_rows"] == 0
    assert result["tables"] == {table: 0 for table in TABLES}


def test_ground_truth_export_writes_persisted_labels(tmp_path: Path):
    from backend.anomaly.injector import AnomalyInjector
    from backend.config import DEFAULT_SEED, GenerationMode
    from backend.generators.generate_data import run_generation

    db_path = tmp_path / "ground_truth.db"
    run_generation(GenerationMode.STARTER, db_path, DEFAULT_SEED, reset=False)
    labels = AnomalyInjector(db_path).inject_all()

    paths = export_ground_truth(db_path, tmp_path / "exports", seed=17)

    with paths["csv"].open(encoding="utf-8", newline="") as file:
        exported_labels = list(csv.DictReader(file))
    exported_json = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert len(labels) == len(exported_labels) == len(exported_json) == 5
    assert {label["issue_type"] for label in exported_json} == {
        label.issue_type for label in labels
    }


def test_export_downloads_include_tables_and_ground_truth(tmp_path: Path, monkeypatch):
    from backend.anomaly.injector import AnomalyInjector
    from backend.config import DEFAULT_SEED, GenerationMode
    from backend.generators.generate_data import run_generation

    db_path = tmp_path / "download.db"
    run_generation(GenerationMode.STARTER, db_path, DEFAULT_SEED, reset=False)
    labels = AnomalyInjector(db_path).inject_all()
    connection = sqlite3.connect(db_path)
    payment_count = connection.execute(
        "SELECT COUNT(*) FROM Payments"
    ).fetchone()[0]
    connection.close()
    export_root = tmp_path / "exports"
    monkeypatch.setattr(export_routes, "EXPORT_ROOT", export_root)

    with _client_for_database(db_path) as client:
        csv_response = client.get("/api/v1/export/csv/download")
        json_response = client.get("/api/v1/export/json/download")

    assert csv_response.status_code == json_response.status_code == 200
    assert csv_response.headers["content-type"] == "application/zip"
    assert "yottaflex-csv-export.zip" in csv_response.headers["content-disposition"]
    assert "yottaflex-json-export.zip" in json_response.headers["content-disposition"]

    for response, extension in ((csv_response, ".csv"), (json_response, ".json")):
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            expected = {f"{table}{extension}" for table in TABLES}
            expected.add(f"ground_truth{extension}")
            assert names == expected

            if extension == ".csv":
                with archive.open("Payments.csv") as file:
                    assert len(
                        list(csv.DictReader(io.TextIOWrapper(file, encoding="utf-8")))
                    ) == payment_count
            else:
                assert len(json.loads(archive.read("Payments.json"))) == payment_count
            if extension == ".json":
                downloaded_labels = json.loads(archive.read("ground_truth.json"))
            else:
                with archive.open("ground_truth.csv") as file:
                    downloaded_labels = list(
                        csv.DictReader(io.TextIOWrapper(file, encoding="utf-8"))
                    )
            assert len(downloaded_labels) == len(labels) == 5


def test_persisted_ground_truth_export_does_not_inject_more_anomalies(tmp_path: Path):
    from backend.anomaly.injector import AnomalyInjector
    from backend.config import DEFAULT_SEED, GenerationMode
    from backend.generators.generate_data import run_generation

    db_path = tmp_path / "persisted-ground-truth.db"
    run_generation(GenerationMode.STARTER, db_path, DEFAULT_SEED, reset=False)
    labels = AnomalyInjector(db_path).inject_all()
    before = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM AuditEvents"
    ).fetchone()[0]

    paths = export_persisted_ground_truth(db_path, tmp_path / "exports")

    after = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM AuditEvents"
    ).fetchone()[0]
    assert before == after
    assert len(json.loads(paths["json"].read_text(encoding="utf-8"))) == len(labels) == 5


def test_persisted_ground_truth_export_rejects_missing_labels(tmp_path: Path):
    db_path = tmp_path / "missing-ground-truth.db"
    DatabaseManager(db_path).initialise()

    with pytest.raises(
        RuntimeError,
        match="all five required anomaly labels",
    ):
        export_persisted_ground_truth(db_path, tmp_path / "exports")


def test_dashboard_does_not_net_one_students_overpayment_against_another(
    tmp_path: Path,
):
    db_path = tmp_path / "balances.db"
    DatabaseManager(db_path).initialise()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO Terms (term_code, term_name, start_date, end_date) "
        "VALUES ('T1', 'Term 1', '2025-01-01', '2025-06-01')"
    )
    conn.execute(
        "INSERT INTO Programs (program_code, program_name, duration_years, level) "
        "VALUES ('P1', 'Program 1', 4, 'UG')"
    )
    for student_id in range(1, 3):
        conn.execute(
            """INSERT INTO Students
               (student_code, first_name, last_name, date_of_birth, email)
               VALUES (?, 'Test', 'Student', '2000-01-01', ?)""",
            (f"STU-{student_id}", f"student{student_id}@example.test"),
        )
        conn.execute(
            """INSERT INTO Enrollments
               (student_id, program_id, term_id, enrollment_date)
               VALUES (?, 1, 1, '2025-01-01')""",
            (student_id,),
        )
        conn.execute(
            """INSERT INTO Invoices
               (invoice_number, enrollment_id, term_id, issue_date, due_date)
               VALUES (?, ?, 1, '2025-01-01', '2025-02-01')""",
            (f"INV-{student_id}", student_id),
        )

    conn.execute(
        """INSERT INTO InvoiceLines
           (invoice_id, fee_type, amount_paise)
           VALUES (1, 'Tuition', 100)"""
    )
    conn.execute(
        """INSERT INTO InvoiceLines
           (invoice_id, fee_type, amount_paise)
           VALUES (2, 'Tuition', 200)"""
    )
    conn.execute(
        """INSERT INTO InvoiceLines
           (invoice_id, fee_type, amount_paise, is_scholarship_credit)
           VALUES (2, 'Scholarship Credit', -150, 1)"""
    )
    conn.execute(
        """INSERT INTO Payments
           (payment_reference, student_id, payment_date, amount_paise,
            payment_method, status)
           VALUES ('PAY-2', 2, '2025-01-01', 100, 'UPI', 'cleared')"""
    )
    conn.execute(
        """INSERT INTO PaymentAllocations
           (payment_id, line_id, allocated_amount_paise)
           VALUES (1, 2, 100)"""
    )
    conn.commit()
    conn.close()

    with _client_for_database(db_path) as client:
        response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["outstanding_paise"] == 100
