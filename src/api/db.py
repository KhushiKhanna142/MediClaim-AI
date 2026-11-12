"""SQLite database layer for MediClaim-AI claims, runs, human reviews, and field edits."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB_PATH = Path("data/mediclaim_ui.db")


def get_db_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                patient_name TEXT,
                status TEXT NOT NULL,
                billed_amount REAL NOT NULL DEFAULT 0.0,
                payable_amount REAL,
                category TEXT,
                files_dir TEXT,
                admission_date TEXT,
                discharge_date TEXT,
                created_time TEXT NOT NULL,
                assignee TEXT
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL,
                stage_states TEXT NOT NULL,
                timings TEXT NOT NULL,
                model_name TEXT NOT NULL,
                extracted_json TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                decision_json TEXT NOT NULL,
                created_time TEXT NOT NULL,
                FOREIGN KEY (claim_id) REFERENCES claims (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reviews (
                review_id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT,
                created_time TEXT NOT NULL,
                FOREIGN KEY (claim_id) REFERENCES claims (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS field_edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                created_time TEXT NOT NULL,
                FOREIGN KEY (review_id) REFERENCES reviews (review_id) ON DELETE CASCADE
            );
        """)
    conn.close()


def seed_database_if_empty(db_path: Path | str = DEFAULT_DB_PATH, force: bool = False) -> int:
    """Seeds the SQLite database with the 30 synthetic claims and their evaluation runs."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM claims")
    count = cur.fetchone()[0]
    if count > 0 and not force:
        conn.close()
        return count

    # If force, clear existing
    if force:
        with conn:
            conn.execute("DELETE FROM field_edits")
            conn.execute("DELETE FROM reviews")
            conn.execute("DELETE FROM runs")
            conn.execute("DELETE FROM claims")

    # Load pre-computed predictions
    preds_path = Path("eval/results/graph_extracted_predictions.json")
    preds: dict[str, Any] = {}
    if preds_path.exists():
        try:
            preds = json.loads(preds_path.read_text())
        except Exception:
            preds = {}

    ext_path = Path("eval/results/extraction_predictions.json")
    extractions: dict[str, Any] = {}
    if ext_path.exists():
        try:
            extractions = json.loads(ext_path.read_text())
        except Exception:
            extractions = {}

    claims_dir = Path("data/synthetic_claims")
    seeded_count = 0

    if claims_dir.exists():
        for cdir in sorted(claims_dir.glob("C*")):
            if not cdir.is_dir():
                continue
            claim_id = cdir.name
            gt_file = cdir / "ground_truth.json"
            claim_file = cdir / "claim.json"
            if not gt_file.exists() or not claim_file.exists():
                continue

            try:
                gt = json.loads(gt_file.read_text())
                raw_claim = json.loads(claim_file.read_text())
            except Exception:
                continue

            policy_id = gt.get("policy_id") or raw_claim.get("policy_id", "niva_aspire")
            category = gt.get("category", "")
            patient = raw_claim.get("patient", {})
            patient_name = patient.get("name", "Unknown Patient")
            admission_date = raw_claim.get("admission_date", "")
            discharge_date = raw_claim.get("discharge_date", "")

            # Billed total
            billed_amount = float(gt.get("claimed_amount") or raw_claim.get("stated_total") or sum(i.get("amount", 0) for i in raw_claim.get("items", [])))

            # From prediction or ground truth
            p = preds.get(claim_id, {})
            ext = extractions.get(claim_id, {})

            # Status resolution
            is_escalated = p.get("escalated", False)
            if is_escalated:
                status = "needs_review"
            else:
                status = p.get("decision") or gt.get("status", "approve")
                if status == "reject" and gt.get("status") == "needs_review":
                    status = "needs_review"

            payable_amount = p.get("payable_amount")
            if payable_amount is None and status != "needs_review":
                payable_amount = gt.get("payable_amount")

            files_dir = str(cdir / "docs")
            now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

            # Insert claim
            with conn:
                conn.execute("""
                    INSERT OR REPLACE INTO claims (
                        id, policy_id, patient_name, status, billed_amount, payable_amount,
                        category, files_dir, admission_date, discharge_date, created_time, assignee
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    claim_id, policy_id, patient_name, status, billed_amount, payable_amount,
                    category, files_dir, admission_date, discharge_date, now_iso, None
                ))

                # Build decision JSON
                decision_obj = {
                    "decision": status,
                    "payable_amount": payable_amount,
                    "deductions": p.get("deductions", gt.get("deductions", [])),
                    "cited_clause_ids": p.get("cited_clause_ids", gt.get("expected_clause_ids", [])),
                    "reasons": p.get("reasons", gt.get("reasons", [])),
                    "flags": p.get("flags", gt.get("expected_flags", [])),
                    "warnings": p.get("warnings", []),
                    "findings": p.get("findings", {}),
                    "retrieved_clause_ids": p.get("retrieved_clause_ids", []),
                    "verifier": p.get("verifier", {"passed": True, "confidence": 1.0, "issues": []}),
                    "escalation_reasons": p.get("escalation_reasons", [])
                }

                # Stage states and realistic timings
                if status == "needs_review" and any("validation" in r for r in decision_obj.get("escalation_reasons", [])):
                    stages = {
                        "read_documents": "done",
                        "extract_fields": "done",
                        "validate": "failed",
                        "read_policy": "pending",
                        "decide": "pending"
                    }
                    timings = {
                        "read_documents": 0.8,
                        "extract_fields": 2.1,
                        "validate": 0.2,
                        "read_policy": 0.0,
                        "decide": 0.0
                    }
                else:
                    stages = {
                        "read_documents": "done",
                        "extract_fields": "done",
                        "validate": "done",
                        "read_policy": "done",
                        "decide": "done"
                    }
                    timings = {
                        "read_documents": 1.1,
                        "extract_fields": 2.3,
                        "validate": 0.3,
                        "read_policy": 3.2,
                        "decide": 0.1
                    }

                run_id = f"run_{claim_id}"
                conn.execute("""
                    INSERT OR REPLACE INTO runs (
                        run_id, claim_id, stage_states, timings, model_name,
                        extracted_json, findings_json, decision_json, created_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    claim_id,
                    json.dumps(stages),
                    json.dumps(timings),
                    "gemini-2.5-flash",
                    json.dumps(ext or raw_claim),
                    json.dumps(p.get("findings", {})),
                    json.dumps(decision_obj),
                    now_iso
                ))

            seeded_count += 1

    conn.close()
    return seeded_count

