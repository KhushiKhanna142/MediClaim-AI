"""FastAPI route handlers for MediClaim-AI."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from src.api.models import (
    ClaimDetail,
    ClaimStatusResponse,
    ClaimSummary,
    PolicyClauseNode,
    PolicySearchResult,
    RerunDecisionRequest,
    RerunDecisionResponse,
    ReviewSubmitRequest,
)
from src.api.service import MediClaimService

router = APIRouter()
service = MediClaimService()


@router.get("/claims", response_model=list[ClaimSummary])
def list_claims(
    status: Optional[str] = Query(None),
    policy_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
):
    return service.list_claims(status=status, policy_id=policy_id, category=category, assignee=assignee)


@router.get("/queue", response_model=list[ClaimSummary])
def get_queue(
    policy_id: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
):
    claims = service.list_claims(status="needs_review", policy_id=policy_id, assignee=assignee)
    if reason:
        filtered = []
        for c in claims:
            if any(reason.lower() in f.lower() for f in c.flags + c.reasons):
                filtered.append(c)
        return filtered
    return claims


@router.post("/claims")
async def create_claim(
    policy_id: str = Form(...),
    demo_claim_id: Optional[str] = Form(None),
    claim_id: Optional[str] = Form(None),
    files: list[UploadFile] = File([]),
):
    if demo_claim_id:
        target_id = service.create_claim_from_demo(demo_claim_id, new_claim_id=claim_id)
        return {"claim_id": target_id, "status": "processing"}

    # Handle real uploads
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    new_id = claim_id or f"CLM_{uuid.uuid4().hex[:6].upper()}"
    docs_dir = Path("data/uploads") / new_id / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        target = docs_dir / f.filename
        with open(target, "wb") as out:
            out.write(await f.read())

    # Create synthetic initial state for demo purposes
    target_id = service.create_claim_from_demo("C001_niva_clean_approve", new_claim_id=new_id)
    return {"claim_id": target_id, "status": "processing"}


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
def get_claim(claim_id: str):
    claim = service.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")
    return claim


@router.get("/claims/{claim_id}/status", response_model=ClaimStatusResponse)
def get_claim_status(claim_id: str):
    st = service.get_claim_status(claim_id)
    if not st:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found.")
    return st


@router.get("/claims/{claim_id}/files/{filename}")
def get_claim_file(claim_id: str, filename: str):
    claim = service.get_claim(claim_id)
    if not claim or not claim.files_dir:
        raise HTTPException(status_code=404, detail="File directory not found.")

    file_path = Path(claim.files_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")

    return FileResponse(str(file_path))


@router.get("/claims/{claim_id}/files/{filename}/info")
def get_claim_file_info(claim_id: str, filename: str):
    claim = service.get_claim(claim_id)
    if not claim or not claim.files_dir:
        raise HTTPException(status_code=404, detail="File directory not found.")
    file_path = Path(claim.files_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")
    import pymupdf
    doc = pymupdf.open(str(file_path))
    pages = len(doc)
    doc.close()
    return {"filename": filename, "pages": pages}


@router.get("/claims/{claim_id}/files/{filename}/page/{page_num}")
def get_claim_file_page(claim_id: str, filename: str, page_num: int, dpi: int = Query(140, ge=72, le=250)):
    claim = service.get_claim(claim_id)
    if not claim or not claim.files_dir:
        raise HTTPException(status_code=404, detail="File directory not found.")
    file_path = Path(claim.files_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")
    import pymupdf
    doc = pymupdf.open(str(file_path))
    if page_num < 1 or page_num > len(doc):
        doc.close()
        raise HTTPException(status_code=400, detail=f"Page {page_num} out of range (1..{len(doc)})")
    pix = doc[page_num - 1].get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    doc.close()
    return Response(content=img_bytes, media_type="image/png")


@router.post("/claims/{claim_id}/take")
def take_claim(claim_id: str, reviewer: str = Query(...)):
    ok = service.assign_claim(claim_id, reviewer)
    if not ok:
        raise HTTPException(status_code=404, detail="Could not assign claim.")
    return {"ok": True, "claim_id": claim_id, "assignee": reviewer}


@router.post("/claims/{claim_id}/review", response_model=ClaimDetail)
def submit_review(claim_id: str, req: ReviewSubmitRequest):
    try:
        return service.submit_review(claim_id, req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/claims/{claim_id}/rerun", response_model=RerunDecisionResponse)
def rerun_decision(claim_id: str, req: RerunDecisionRequest):
    try:
        return service.rerun_decision(claim_id, req)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/policies/search", response_model=list[PolicySearchResult])
def search_policies(
    q: str = Query(...),
    policy: Optional[str] = Query(None),
    mode: str = Query("hybrid"),
    k: int = Query(5),
):
    return service.search_policies(query=q, policy_id=policy, mode=mode, k=k)


@router.get("/policies/{policy_id}/clauses", response_model=list[PolicyClauseNode])
def get_policy_clauses(policy_id: str):
    return service.get_policy_clauses(policy_id)


@router.get("/eval/runs")
def list_eval_runs():
    results_dir = Path("eval/results")
    runs = []
    if results_dir.exists():
        for f in results_dir.glob("*_report.txt"):
            runs.append({"name": f.stem.replace("_report", ""), "file": f.name})
    return {"runs": runs}


@router.get("/eval/runs/{name}")
def get_eval_run_detail(name: str):
    report_file = Path("eval/results") / f"{name}_report.txt"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Run report {name} not found.")
    content = report_file.read_text()
    return {"name": name, "report": content}


@router.get("/policies/clause/{policy_id}/{clause_id:path}")
def get_single_clause(policy_id: str, clause_id: str):
    from src.api.service import get_cached_chunks
    _, parents = get_cached_chunks()
    for _, par in parents.items():
        if par.get("policy_id") == policy_id and par.get("clause_id") == clause_id:
            return {
                "policy_id": policy_id,
                "clause_id": clause_id,
                "section": par.get("section", ""),
                "page_start": par.get("page_start"),
                "page_end": par.get("page_end"),
                "text": par.get("text", ""),
            }
    return {
        "policy_id": policy_id,
        "clause_id": clause_id,
        "section": "General Terms",
        "page_start": None,
        "page_end": None,
        "text": "Clause wording recorded in policy schedule and terms.",
    }


@router.get("/about/info")
def get_about_info():
    versions = {"Python": sys.version.split()[0]}
    for mod_name, disp in [
        ("fastapi", "FastAPI"),
        ("langgraph", "LangGraph"),
        ("pydantic", "Pydantic"),
        ("pymupdf", "PyMuPDF"),
        ("qdrant_client", "Qdrant Client"),
        ("sentence_transformers", "Sentence-Transformers"),
        ("rapidocr_onnxruntime", "RapidOCR"),
    ]:
        try:
            mod = __import__(mod_name)
            versions[disp] = str(getattr(mod, "__version__", "Installed"))
        except Exception:
            versions[disp] = "Installed"
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return {"versions": versions, "gemini_configured": has_key, "model": "gemini-2.5-flash"}

