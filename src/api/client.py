"""Client abstraction for MediClaim-AI frontend. Supports HTTP or direct in-process service calls."""
from __future__ import annotations

import os
from typing import Any, Optional

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

API_BASE_URL = os.environ.get("MEDICLAIM_API_URL", "http://127.0.0.1:8000")


class ApiClient:
    def __init__(self, base_url: str = API_BASE_URL, use_http: bool = False):
        self.base_url = base_url.rstrip("/")
        self.use_http = use_http
        self._service = MediClaimService()

    def list_claims(
        self,
        status: Optional[str] = None,
        policy_id: Optional[str] = None,
        category: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> list[ClaimSummary]:
        if self.use_http:
            import requests

            params = {}
            if status:
                params["status"] = status
            if policy_id:
                params["policy_id"] = policy_id
            if category:
                params["category"] = category
            if assignee:
                params["assignee"] = assignee
            try:
                r = requests.get(f"{self.base_url}/claims", params=params, timeout=5)
                if r.status_code == 200:
                    return [ClaimSummary.model_validate(x) for x in r.json()]
            except Exception:
                pass
        return self._service.list_claims(status=status, policy_id=policy_id, category=category, assignee=assignee)

    def get_queue(
        self,
        policy_id: Optional[str] = None,
        reason: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> list[ClaimSummary]:
        claims = self.list_claims(status="needs_review", policy_id=policy_id, assignee=assignee)
        if reason:
            return [c for c in claims if any(reason.lower() in f.lower() for f in c.flags + c.reasons)]
        return claims

    def get_claim(self, claim_id: str) -> Optional[ClaimDetail]:
        if self.use_http:
            import requests

            try:
                r = requests.get(f"{self.base_url}/claims/{claim_id}", timeout=5)
                if r.status_code == 200:
                    return ClaimDetail.model_validate(r.json())
            except Exception:
                pass
        return self._service.get_claim(claim_id)

    def get_claim_status(self, claim_id: str) -> Optional[ClaimStatusResponse]:
        if self.use_http:
            import requests

            try:
                r = requests.get(f"{self.base_url}/claims/{claim_id}/status", timeout=5)
                if r.status_code == 200:
                    return ClaimStatusResponse.model_validate(r.json())
            except Exception:
                pass
        return self._service.get_claim_status(claim_id)

    def assign_claim(self, claim_id: str, reviewer: str) -> bool:
        if self.use_http:
            import requests

            try:
                r = requests.post(
                    f"{self.base_url}/claims/{claim_id}/take",
                    params={"reviewer": reviewer},
                    timeout=5,
                )
                if r.status_code == 200:
                    return True
            except Exception:
                pass
        return self._service.assign_claim(claim_id, reviewer)

    def submit_demo_claim(self, demo_claim_id: str, target_claim_id: Optional[str] = None) -> str:
        return self._service.create_claim_from_demo(demo_claim_id, new_claim_id=target_claim_id)

    def submit_review(self, claim_id: str, req: ReviewSubmitRequest) -> ClaimDetail:
        if self.use_http:
            import requests

            try:
                r = requests.post(
                    f"{self.base_url}/claims/{claim_id}/review",
                    json=req.model_dump(),
                    timeout=10,
                )
                if r.status_code == 200:
                    return ClaimDetail.model_validate(r.json())
            except Exception:
                pass
        return self._service.submit_review(claim_id, req)

    def rerun_decision(self, claim_id: str, field_updates: dict[str, Any]) -> RerunDecisionResponse:
        req = RerunDecisionRequest(field_updates=field_updates)
        if self.use_http:
            import requests

            try:
                r = requests.post(
                    f"{self.base_url}/claims/{claim_id}/rerun",
                    json=req.model_dump(),
                    timeout=10,
                )
                if r.status_code == 200:
                    return RerunDecisionResponse.model_validate(r.json())
            except Exception:
                pass
        return self._service.rerun_decision(claim_id, req)

    def search_policies(
        self,
        query: str,
        policy_id: Optional[str] = None,
        mode: str = "hybrid",
        k: int = 5,
    ) -> list[PolicySearchResult]:
        if self.use_http:
            import requests

            try:
                params = {"q": query, "mode": mode, "k": k}
                if policy_id and policy_id != "all":
                    params["policy"] = policy_id
                r = requests.get(f"{self.base_url}/policies/search", params=params, timeout=10)
                if r.status_code == 200:
                    return [PolicySearchResult.model_validate(x) for x in r.json()]
            except Exception:
                pass
        return self._service.search_policies(query=query, policy_id=policy_id, mode=mode, k=k)

    def get_policy_clauses(self, policy_id: str) -> list[PolicyClauseNode]:
        if self.use_http:
            import requests

            try:
                r = requests.get(f"{self.base_url}/policies/{policy_id}/clauses", timeout=5)
                if r.status_code == 200:
                    return [PolicyClauseNode.model_validate(x) for x in r.json()]
            except Exception:
                pass
        return self._service.get_policy_clauses(policy_id)


def get_client() -> ApiClient:
    return ApiClient()

