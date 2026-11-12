"""Core business logic and service layer for MediClaim-AI backend."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.adjudication.engine import decide
from src.adjudication.findings import Findings
from src.api.db import DEFAULT_DB_PATH, get_db_connection, seed_database_if_empty
from src.api.models import (
    ClaimDetail,
    ClaimStatusResponse,
    ClaimSummary,
    DecisionDetail,
    DeductionItem,
    PolicyClauseNode,
    PolicySearchResult,
    RerunDecisionRequest,
    RerunDecisionResponse,
    ReviewAuditEntry,
    ReviewSubmitRequest,
)
from src.extraction.schemas import ExtractedClaim
from src.rag.index import load_chunks
from src.validation.checks import docs_in_dir, validate

# Cached policy chunks and retriever
_CACHED_CHUNKS: Optional[tuple[list[dict], dict[str, dict]]] = None
_CACHED_RETRIEVER = None


def get_cached_chunks() -> tuple[list[dict], dict[str, dict]]:
    global _CACHED_CHUNKS
    if _CACHED_CHUNKS is None:
        chunks_dir = Path("data/processed/chunks")
        if chunks_dir.exists():
            _CACHED_CHUNKS = load_chunks(str(chunks_dir))
        else:
            _CACHED_CHUNKS = ([], {})
    return _CACHED_CHUNKS


def get_cached_retriever():
    global _CACHED_RETRIEVER
    if _CACHED_RETRIEVER is None:
        try:
            # Set HF offline mode for fast local loading
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from qdrant_client import QdrantClient
            from src.rag.embedder import get_embedder
            from src.rag.retriever import HybridRetriever

            qdrant_path = "data/qdrant"
            client = QdrantClient(path=qdrant_path) if Path(qdrant_path).exists() else QdrantClient(":memory:")
            children, parents = get_cached_chunks()
            embedder = get_embedder("BAAI/bge-small-en-v1.5")
            _CACHED_RETRIEVER = HybridRetriever(client, embedder, children, parents)
        except Exception:
            # If Qdrant/embedding fails, fallback will be handled gracefully in search_policies
            _CACHED_RETRIEVER = None
    return _CACHED_RETRIEVER


class MediClaimService:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        seed_database_if_empty(self.db_path)

    def list_claims(
        self,
        status: Optional[str] = None,
        policy_id: Optional[str] = None,
        category: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> list[ClaimSummary]:
        conn = get_db_connection(self.db_path)
        query = "SELECT c.*, r.decision_json FROM claims c LEFT JOIN runs r ON c.id = r.claim_id WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND c.status = ?"
            params.append(status)
        if policy_id:
            query += " AND c.policy_id = ?"
            params.append(policy_id)
        if category:
            query += " AND c.category = ?"
            params.append(category)
        if assignee:
            query += " AND c.assignee = ?"
            params.append(assignee)

        query += " ORDER BY c.id ASC"
        rows = conn.execute(query, params).fetchall()
        summaries: list[ClaimSummary] = []

        for row in rows:
            flags: list[str] = []
            reasons: list[str] = []
            if row["decision_json"]:
                try:
                    dec = json.loads(row["decision_json"])
                    flags = dec.get("flags", []) or dec.get("escalation_reasons", [])
                    reasons = dec.get("reasons", [])
                except Exception:
                    pass

            summaries.append(
                ClaimSummary(
                    id=row["id"],
                    policy_id=row["policy_id"],
                    patient_name=row["patient_name"],
                    status=row["status"],
                    billed_amount=float(row["billed_amount"]),
                    payable_amount=float(row["payable_amount"]) if row["payable_amount"] is not None else None,
                    category=row["category"],
                    created_time=row["created_time"],
                    assignee=row["assignee"],
                    flags=flags,
                    reasons=reasons,
                )
            )

        conn.close()
        return summaries

    def get_claim(self, claim_id: str) -> Optional[ClaimDetail]:
        conn = get_db_connection(self.db_path)
        crow = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not crow:
            conn.close()
            return None

        rrow = conn.execute(
            "SELECT * FROM runs WHERE claim_id = ? ORDER BY created_time DESC LIMIT 1",
            (claim_id,),
        ).fetchone()

        # Files list
        files: list[str] = []
        if crow["files_dir"] and Path(crow["files_dir"]).exists():
            files = sorted(f.name for f in Path(crow["files_dir"]).glob("*.pdf"))

        # Decision & Extracted
        decision: Optional[DecisionDetail] = None
        extracted: Optional[dict[str, Any]] = None
        stage_states: Optional[dict[str, str]] = None
        timings: Optional[dict[str, float]] = None

        if rrow:
            try:
                dec_dict = json.loads(rrow["decision_json"])
                deductions = [
                    DeductionItem(
                        rule=d.get("rule", "other"),
                        amount=float(d.get("amount", 0.0)),
                        clause_id=d.get("clause_id"),
                        note=d.get("note"),
                    )
                    for d in dec_dict.get("deductions", [])
                ]
                decision = DecisionDetail(
                    decision=dec_dict.get("decision", crow["status"]),
                    payable_amount=dec_dict.get("payable_amount"),
                    deductions=deductions,
                    cited_clause_ids=dec_dict.get("cited_clause_ids", []),
                    reasons=dec_dict.get("reasons", []),
                    flags=dec_dict.get("flags", []),
                    warnings=dec_dict.get("warnings", []),
                    findings=dec_dict.get("findings", {}),
                    retrieved_clause_ids=dec_dict.get("retrieved_clause_ids", []),
                    verifier=dec_dict.get("verifier"),
                    escalation_reasons=dec_dict.get("escalation_reasons", []),
                )
            except Exception:
                pass

            try:
                extracted = json.loads(rrow["extracted_json"])
            except Exception:
                pass

            try:
                stage_states = json.loads(rrow["stage_states"])
            except Exception:
                pass

            try:
                timings = json.loads(rrow["timings"])
            except Exception:
                pass

        # Reviews & field edits
        rev_rows = conn.execute(
            "SELECT * FROM reviews WHERE claim_id = ? ORDER BY created_time ASC",
            (claim_id,),
        ).fetchall()
        timeline: list[ReviewAuditEntry] = []

        for rev in rev_rows:
            fe_rows = conn.execute(
                "SELECT * FROM field_edits WHERE review_id = ?",
                (rev["review_id"],),
            ).fetchall()
            edits = [
                {
                    "field_name": fe["field_name"],
                    "old_value": fe["old_value"],
                    "new_value": fe["new_value"],
                }
                for fe in fe_rows
            ]
            timeline.append(
                ReviewAuditEntry(
                    review_id=rev["review_id"],
                    claim_id=rev["claim_id"],
                    reviewer=rev["reviewer"],
                    action=rev["action"],
                    reason=rev["reason"],
                    created_time=rev["created_time"],
                    field_edits=edits,
                )
            )

        conn.close()

        return ClaimDetail(
            id=crow["id"],
            policy_id=crow["policy_id"],
            patient_name=crow["patient_name"],
            status=crow["status"],
            billed_amount=float(crow["billed_amount"]),
            payable_amount=float(crow["payable_amount"]) if crow["payable_amount"] is not None else None,
            category=crow["category"],
            files_dir=crow["files_dir"],
            files=files,
            admission_date=crow["admission_date"],
            discharge_date=crow["discharge_date"],
            created_time=crow["created_time"],
            assignee=crow["assignee"],
            decision=decision,
            extracted=extracted,
            stage_states=stage_states,
            timings=timings,
            audit_timeline=timeline,
        )

    def get_claim_status(self, claim_id: str) -> Optional[ClaimStatusResponse]:
        conn = get_db_connection(self.db_path)
        row = conn.execute(
            "SELECT c.status, r.stage_states, r.timings FROM claims c LEFT JOIN runs r ON c.id = r.claim_id WHERE c.id = ? ORDER BY r.created_time DESC LIMIT 1",
            (claim_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        stage_states = json.loads(row["stage_states"]) if row["stage_states"] else {}
        timings = json.loads(row["timings"]) if row["timings"] else {}

        # Determine current stage or message
        current_stage = None
        message = None
        for stage in ["read_documents", "extract_fields", "validate", "read_policy", "decide"]:
            st = stage_states.get(stage, "pending")
            if st == "running":
                current_stage = stage
                message = f"Executing {stage.replace('_', ' ')}..."
                break
            elif st == "failed":
                current_stage = stage
                message = f"Stage {stage} raised validation flag or error."
                break

        if not current_stage:
            current_stage = "completed" if row["status"] != "needs_review" else "review"
            message = "Processing completed." if row["status"] != "needs_review" else "Claim sent to human review queue."

        return ClaimStatusResponse(
            claim_id=claim_id,
            status=row["status"],
            stage_states=stage_states,
            timings=timings,
            current_stage=current_stage,
            message=message,
        )

    def assign_claim(self, claim_id: str, reviewer: str) -> bool:
        conn = get_db_connection(self.db_path)
        with conn:
            cur = conn.execute("UPDATE claims SET assignee = ? WHERE id = ?", (reviewer, claim_id))
            updated = cur.rowcount > 0
        conn.close()
        return updated

    def create_claim_from_demo(self, demo_claim_id: str, new_claim_id: Optional[str] = None) -> str:
        """Clones a synthetic claim into a new claim entry for live submission demo."""
        source_dir = Path("data/synthetic_claims") / demo_claim_id
        if not source_dir.exists():
            raise ValueError(f"Demo claim {demo_claim_id} not found.")

        target_id = new_claim_id or f"SUB_{demo_claim_id}_{datetime.now().strftime('%M%S')}"
        upload_docs_dir = Path("data/uploads") / target_id / "docs"
        upload_docs_dir.mkdir(parents=True, exist_ok=True)

        # Copy documents
        src_docs = source_dir / "docs"
        if src_docs.exists():
            for f in src_docs.glob("*.pdf"):
                shutil.copy2(f, upload_docs_dir / f.name)

        # Copy raw claim and ground truth
        gt = json.loads((source_dir / "ground_truth.json").read_text())
        raw_claim = json.loads((source_dir / "claim.json").read_text())

        # Load prediction if available
        preds_path = Path("eval/results/graph_extracted_predictions.json")
        pred = {}
        if preds_path.exists():
            try:
                preds = json.loads(preds_path.read_text())
                pred = preds.get(demo_claim_id, {})
            except Exception:
                pass

        ext_path = Path("eval/results/extraction_predictions.json")
        extracted = {}
        if ext_path.exists():
            try:
                exts = json.loads(ext_path.read_text())
                extracted = exts.get(demo_claim_id, raw_claim)
            except Exception:
                extracted = raw_claim

        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        status = pred.get("decision") or gt.get("status", "approve")
        if pred.get("escalated"):
            status = "needs_review"

        billed_amount = float(gt.get("claimed_amount") or raw_claim.get("stated_total") or 0.0)
        payable_amount = pred.get("payable_amount") if status != "needs_review" else None

        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO claims (
                    id, policy_id, patient_name, status, billed_amount, payable_amount,
                    category, files_dir, admission_date, discharge_date, created_time, assignee
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    target_id,
                    gt.get("policy_id", "niva_aspire"),
                    raw_claim.get("patient", {}).get("name", "Demo Patient"),
                    "pending",  # starts in pending for processing view
                    billed_amount,
                    payable_amount,
                    gt.get("category", ""),
                    str(upload_docs_dir),
                    raw_claim.get("admission_date", ""),
                    raw_claim.get("discharge_date", ""),
                    now_iso,
                    None,
                ),
            )

            decision_obj = {
                "decision": status,
                "payable_amount": payable_amount,
                "deductions": pred.get("deductions", gt.get("deductions", [])),
                "cited_clause_ids": pred.get("cited_clause_ids", gt.get("expected_clause_ids", [])),
                "reasons": pred.get("reasons", gt.get("reasons", [])),
                "flags": pred.get("flags", gt.get("expected_flags", [])),
                "warnings": pred.get("warnings", []),
                "findings": pred.get("findings", {}),
                "retrieved_clause_ids": pred.get("retrieved_clause_ids", []),
                "verifier": pred.get("verifier", {"passed": True, "confidence": 1.0, "issues": []}),
                "escalation_reasons": pred.get("escalation_reasons", []),
            }

            stages = {
                "read_documents": "done",
                "extract_fields": "done",
                "validate": "done" if status != "needs_review" else "failed",
                "read_policy": "done" if status != "needs_review" else "pending",
                "decide": "done" if status != "needs_review" else "pending",
            }

            timings = {
                "read_documents": 1.0,
                "extract_fields": 2.2,
                "validate": 0.3,
                "read_policy": 3.1 if status != "needs_review" else 0.0,
                "decide": 0.1 if status != "needs_review" else 0.0,
            }

            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, claim_id, stage_states, timings, model_name,
                    extracted_json, findings_json, decision_json, created_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    f"run_{target_id}",
                    target_id,
                    json.dumps(stages),
                    json.dumps(timings),
                    "gemini-2.5-flash",
                    json.dumps(extracted),
                    json.dumps(pred.get("findings", {})),
                    json.dumps(decision_obj),
                    now_iso,
                ),
            )

        conn.close()
        return target_id

    def submit_review(self, claim_id: str, req: ReviewSubmitRequest) -> ClaimDetail:
        conn = get_db_connection(self.db_path)
        review_id = f"rev_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with conn:
            conn.execute(
                """
                INSERT INTO reviews (review_id, claim_id, reviewer, action, reason, created_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (review_id, claim_id, req.reviewer, req.action, req.reason or "", now_iso),
            )

            # Insert field edits
            for fe in req.field_edits:
                conn.execute(
                    """
                    INSERT INTO field_edits (review_id, claim_id, field_name, old_value, new_value, created_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        review_id,
                        claim_id,
                        fe.field_name,
                        str(fe.old_value),
                        str(fe.new_value),
                        now_iso,
                    ),
                )

            # Determine new status & payable
            rrow = conn.execute(
                "SELECT * FROM runs WHERE claim_id = ? ORDER BY created_time DESC LIMIT 1",
                (claim_id,),
            ).fetchone()
            cur_dec = json.loads(rrow["decision_json"]) if rrow else {}

            if req.action == "confirm":
                new_status = cur_dec.get("decision", "approve")
                new_payable = cur_dec.get("payable_amount")
            elif req.action == "override":
                new_status = req.override_status or "approve"
                new_payable = req.override_payable if new_status != "reject" else 0.0
            else:  # request_docs
                new_status = "pending_docs"
                new_payable = None

            conn.execute(
                """
                UPDATE claims SET status = ?, payable_amount = ?, assignee = ?
                WHERE id = ?
            """,
                (new_status, new_payable, req.reviewer, claim_id),
            )

        conn.close()
        updated = self.get_claim(claim_id)
        if not updated:
            raise ValueError(f"Claim {claim_id} not found after review.")
        return updated

    def rerun_decision(self, claim_id: str, req: RerunDecisionRequest) -> RerunDecisionResponse:
        """Calls ONLY the deterministic engine, NOT the LLM, to recalculate payout with updated fields."""
        conn = get_db_connection(self.db_path)
        rrow = conn.execute(
            "SELECT * FROM runs WHERE claim_id = ? ORDER BY created_time DESC LIMIT 1",
            (claim_id,),
        ).fetchone()
        crow = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        conn.close()

        if not rrow or not crow:
            raise ValueError(f"Claim {claim_id} not found.")

        extracted_data = json.loads(rrow["extracted_json"])
        findings_data = json.loads(rrow["findings_json"])
        prev_dec = json.loads(rrow["decision_json"])

        # Apply field updates
        for k, v in req.field_updates.items():
            if k in extracted_data:
                extracted_data[k] = v

        # Convert to ExtractedClaim
        c_obj = ExtractedClaim.model_validate(extracted_data)

        # Get docs present
        docs_present = []
        if crow["files_dir"] and Path(crow["files_dir"]).exists():
            p_dir = Path(crow["files_dir"])
            if p_dir.name == "docs":
                docs_present = sorted(p.stem for p in p_dir.glob("*.pdf"))
            else:
                docs_present = docs_in_dir(p_dir)

        # Run validation checks
        val_report = validate(c_obj, docs_present)

        if val_report.needs_review:
            new_decision = "needs_review"
            new_payable = None
            deductions: list[dict[str, Any]] = []
            reasons = val_report.details
            cites = []
        else:
            # Deterministic engine execution: No LLM, pure arithmetic and policy logic
            f_obj = Findings.model_validate(findings_data)
            engine_out = decide(c_obj, f_obj)
            new_decision = engine_out["decision"]
            new_payable = engine_out["payable_amount"]
            deductions = engine_out.get("deductions", [])
            reasons = engine_out.get("reasons", [])
            cites = engine_out.get("cited_clause_ids", [])

        prev_payable = prev_dec.get("payable_amount")
        prev_status = prev_dec.get("decision", crow["status"])
        diff = (new_payable or 0.0) - (prev_payable or 0.0)

        # Update the run with new values
        updated_dec = dict(prev_dec)
        updated_dec["decision"] = new_decision
        updated_dec["payable_amount"] = new_payable
        updated_dec["deductions"] = deductions
        updated_dec["reasons"] = reasons
        updated_dec["cited_clause_ids"] = cites
        updated_dec["flags"] = val_report.flags
        updated_dec["warnings"] = val_report.warnings

        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute(
                """
                UPDATE runs SET extracted_json = ?, decision_json = ?
                WHERE run_id = ?
            """,
                (json.dumps(extracted_data), json.dumps(updated_dec), rrow["run_id"]),
            )
            # Update claim table
            conn.execute(
                """
                UPDATE claims SET status = ?, payable_amount = ? WHERE id = ?
            """,
                (new_decision, new_payable, claim_id),
            )
        conn.close()

        return RerunDecisionResponse(
            claim_id=claim_id,
            previous_decision=prev_status,
            previous_payable=prev_payable,
            new_decision=new_decision,
            new_payable=new_payable,
            deductions=deductions,
            reasons=reasons,
            cited_clause_ids=cites,
            flags=val_report.flags,
            difference=diff,
        )

    def search_policies(
        self,
        query: str,
        policy_id: Optional[str] = None,
        mode: str = "hybrid",
        k: int = 5,
    ) -> list[PolicySearchResult]:
        children, parents = get_cached_chunks()
        if not children:
            return []

        # If specific policy filter
        allowed_policies = [policy_id] if policy_id and policy_id != "all" else None

        retriever = get_cached_retriever()
        if retriever is not None:
            try:
                raw_results = retriever.search(
                    query=query,
                    k=k,
                    policy_ids=allowed_policies,
                    mode=mode if mode in ("dense", "hybrid", "bm25") else "hybrid",
                )
                return [
                    PolicySearchResult(
                        policy_id=r["policy_id"],
                        clause_id=r["clause_id"],
                        parent_id=r.get("parent_id"),
                        section=r.get("section", ""),
                        page_start=r.get("page_start"),
                        page_end=r.get("page_end"),
                        score=float(r.get("score", 0.0)),
                        child_text=r.get("child_text"),
                        text=r.get("text", ""),
                        retriever_source=mode,
                    )
                    for r in raw_results
                ]
            except Exception:
                pass

        # Fallback keyword search across loaded chunks
        q_tokens = [w.lower() for w in query.split() if len(w) > 2]
        scored_parents = []
        for pid, par in parents.items():
            if allowed_policies and par.get("policy_id") not in allowed_policies:
                continue
            txt = par.get("text", "").lower()
            sc = sum(1.0 for token in q_tokens if token in txt)
            if sc > 0:
                scored_parents.append((sc, par))

        scored_parents.sort(key=lambda x: -x[0])
        results: list[PolicySearchResult] = []
        for sc, par in scored_parents[:k]:
            results.append(
                PolicySearchResult(
                    policy_id=par.get("policy_id", ""),
                    clause_id=par.get("clause_id", ""),
                    parent_id=par.get("chunk_id"),
                    section=par.get("section", ""),
                    page_start=par.get("page_start"),
                    page_end=par.get("page_end"),
                    score=round(float(sc) / max(len(q_tokens), 1), 3),
                    child_text=None,
                    text=par.get("text", ""),
                    retriever_source="bm25_lexical",
                )
            )
        return results

    def get_policy_clauses(self, policy_id: str) -> list[PolicyClauseNode]:
        _, parents = get_cached_chunks()
        nodes: list[PolicyClauseNode] = []
        for _, par in parents.items():
            if par.get("policy_id") == policy_id:
                txt = par.get("text", "").strip()
                preview = txt[:140] + "..." if len(txt) > 140 else txt
                nodes.append(
                    PolicyClauseNode(
                        clause_id=par.get("clause_id", "unknown"),
                        section=par.get("section", ""),
                        page_start=par.get("page_start"),
                        page_end=par.get("page_end"),
                        text=txt,
                        preview=preview,
                    )
                )

        # Sort naturally by clause_id
        nodes.sort(key=lambda n: n.clause_id)
        return nodes
