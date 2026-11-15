# MediClaim-AI — Recent Changes Summary

This document summarizes the UI rebuild, Streamlit removal, and PII masking implementation completed in the repository.

---

## 1. Light-Theme React UI & FastAPI Backend

### What Was Built
- **FastAPI Backend (`src/api/`)**: Added a REST API service with SQLite persistence (`src/api/db.py`), Pydantic models (`src/api/models.py`), service orchestration (`src/api/service.py`), and HTTP routes (`src/api/routes.py`) mounted under `/api` (and `/` for direct API clients) in `src/api/main.py`. It also serves the built React static bundle from `frontend/dist`.
- **Light-Theme React Frontend (`frontend/`)**: Built an 8-view light-theme web application replacing the previous UI:
  - **Submit Claim** (`SubmitPage.jsx`): Upload claim PDFs/documents and select insurer/policy.
  - **Processing** (`ProcessingPage.jsx`): Live claim processing status and step trace.
  - **Decision** (`DecisionPage.jsx`): Claim verdict, payable/claimed/deduction summary, deduction breakdown, cited policy clauses, document viewer, validation flags, and audit timeline.
  - **Review Queue** (`ReviewQueuePage.jsx`): Queue of claims requiring or available for human review.
  - **Review Detail** (`ReviewDetailPage.jsx`): Detailed human-in-the-loop review and override view.
  - **Policy Explorer** (`PolicyExplorerPage.jsx`): Browse and inspect policy clauses and schedules.
  - **Evaluation** (`EvaluationPage.jsx`): View benchmark and evaluation metrics.
  - **About** (`AboutPage.jsx`): System architecture, disclaimer, and metadata.
- **Reusable UI Components (`frontend/src/components/`)**:
  - `AuditTimeline.jsx`
  - `ClauseCard.jsx`
  - `DocumentViewer.jsx`
  - `StatusBadge.jsx`
- **Streamlit UI Removal**: Removed the legacy Streamlit UI application and related references (`src/ui/` now contains only `__init__.py`).

---

## 2. PII Masking Before LLM Calls

### What Was Implemented
- **PII Redaction Module (`src/security/pii.py`)**: Implemented regex-based masking with three helpers exported from `src/security/__init__.py`:
  - `mask_pii(text: str) -> tuple[str, dict[str, int]]`: Redacts sensitive identifiers and returns the masked text along with per-type redaction counts.
  - `redact_pii(text: str) -> str`: Convenience wrapper returning only the redacted string.
  - `mask_dict_pii(obj: Any) -> Any`: Recursively redacts all string values inside nested dicts/lists.
- **Redacted Patterns & Tokens**:
  - Aadhaar numbers → `[AADHAAR_REDACTED]`
  - PAN card numbers → `[PAN_REDACTED]`
  - IFSC codes → `[IFSC_REDACTED]`
  - Email addresses → `[EMAIL_REDACTED]`
  - Indian phone numbers → `[PHONE_REDACTED]`
  - Clinical terms, dates, policy clause IDs, and rupee amounts are preserved.

### Pipeline Integration
- **Extraction (`src/extraction/extract.py`)**: `Extractor.extract_text` wraps `claim_text` with `redact_pii(claim_text)` before sending document text to `self.llm.complete`.
- **Adjudication (`src/adjudication/reader.py`)**: `build_prompt` applies `redact_pii` to `c.diagnosis` and `c.known_history`.
- **Verification (`src/agents/verifier.py`)**: `Verifier._critic` applies `mask_dict_pii(facts)` before serializing claim facts to JSON for `self.llm.complete`.

### Verification
- Added `tests/test_security.py` with 4 unit tests covering Aadhaar, PAN, phone, email, and IFSC masking, preservation of amounts/dates/clause IDs, `mask_dict_pii`, and `Extractor.extract_text`.
- Full test suite (`pytest`) passed: **157 passed** (including `tests/test_security.py` and `tests/test_ui_api.py`).

---

## 3. Tech Stack & Libraries Used

| Layer | Technologies / Libraries |
| :--- | :--- |
| **Frontend** | React (`^19.0.0`), React DOM (`^19.0.0`), Vite (`^6.0.0`), `@vitejs/plugin-react` (`^4.3.4`), Tailwind CSS (`@tailwindcss/vite` `^4.0.0`), `lucide-react` (`^0.468.0`) |
| **Backend API** | FastAPI, Pydantic, SQLite (`sqlite3`), Starlette CORSMiddleware & StaticFiles |
| **PII Security** | Python `re` (regular-expression masking in `src/security/pii.py`) |
| **Testing** | `pytest` |

---

## 4. Updated File Structure

```text
MediClaim-AI/
├── CHANGES.md
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.js
│   ├── dist/                         # Production build served by FastAPI
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       ├── index.css
│       ├── main.jsx
│       ├── components/
│       │   ├── AuditTimeline.jsx
│       │   ├── ClauseCard.jsx
│       │   ├── DocumentViewer.jsx
│       │   └── StatusBadge.jsx
│       ├── pages/
│       │   ├── AboutPage.jsx
│       │   ├── DecisionPage.jsx
│       │   ├── EvaluationPage.jsx
│       │   ├── PolicyExplorerPage.jsx
│       │   ├── ProcessingPage.jsx
│       │   ├── ReviewDetailPage.jsx
│       │   ├── ReviewQueuePage.jsx
│       │   └── SubmitPage.jsx
│       └── utils/
│           └── format.js
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   └── service.py
│   ├── adjudication/
│   │   └── reader.py                 # Wired redact_pii into build_prompt
│   ├── agents/
│   │   └── verifier.py               # Wired mask_dict_pii into Verifier._critic
│   ├── extraction/
│   │   └── extract.py                # Wired redact_pii into Extractor.extract_text
│   ├── security/
│   │   ├── __init__.py
│   │   └── pii.py                    # Regex PII masking (Aadhaar, PAN, IFSC, email, phone)
│   └── ui/
│       └── __init__.py               # Legacy Streamlit UI removed
└── tests/
    ├── test_security.py              # PII masking unit tests (4 tests)
    └── test_ui_api.py                # FastAPI UI backend tests (7 tests)
```

