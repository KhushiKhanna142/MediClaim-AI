# MediClaim-AI: What’s Done vs. What’s Left

> **Document Purpose**: This file organizes and reconciles the project roadmap note against the actual, up-to-date codebase state in `/Users/khushikhanna/Desktop/Projects/MediClaim-AI`.
> **Last Verified**: November 2026 | **Test Suite**: 122 / 122 tests passing (`pytest tests/`)

---

## 🧭 Executive Summary of Progress

Since the earlier project status note was drafted, significant progress has been made:
1. **The Baseline was finished**: Rerun completely on a single model, replacing the older mixed-model run. Citation recall (16%) and precision (19%) were diagnosed and locked into the official "before" benchmark row.
2. **Extraction Eval was run & fixed**: Scanned PDF issues, bill layouts, and date reading were resolved with 300 DPI rendering, RapidOCR table box clustering, and multimodal vision fallback (`fill_with_vision`).
3. **The Validation Layer was built**: [`src/validation/checks.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/validation/checks.py) validates totals, dates, and mandatory documents with zero LLM dependency, routing directly to `needs_review`.
4. **Test Suite expanded**: Grew from the initial 100 tests to **122 passing tests**.

Below is the definitive breakdown of **What’s Done** and **What’s Left**.

---

## ✅ What’s Done

### 1. Data Ingestion & Policy Preprocessing
- [x] **Six Policy Wordings Collected**:
  - Care Health (*Care Supreme*)
  - HDFC ERGO (*Optima Restore Current* & *Optima Restore Old*)
  - HDFC ERGO (*Optima Secure Current*)
  - Niva Bupa (*Aspire*)
  - Star Health (*Star Comprehensive*)
- [x] **Bilingual Unicode Text Stripper** ([`src/ingestion/english_text.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/ingestion/english_text.py)): Removes Devanagari script and Hindi boilerplate from regulatory circulars and policy PDFs without corrupting legal numbers or English tables.
- [x] **Clean Policy Normalizer** ([`src/ingestion/clean_policy_text.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/ingestion/clean_policy_text.py)): Removes repeated page headers, watermarked UINs, broken hyphens, and formats major/sub-headings.
- [x] **Clause-Aware Hierarchical Chunker** ([`src/rag/chunker.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/chunker.py)):
  - Handles 5 distinct insurer numbering layouts (e.g., Niva `5.1.3`, HDFC `Def. 18` / `Section C`, Star definitions).
  - Emits parent clauses ($\le 3,000$ chars) preserving full legal context, and child passages ($\le 900$ chars) for dense vector matching.
  - Ensures retrieved passages are cited with verifiable clause IDs (e.g., `"Niva 5.1.3"`) rather than arbitrary page numbers.

### 2. Hybrid RAG & Regulatory Retrieval
- [x] **Vector Database Indexing** ([`src/rag/index.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/index.py)): Local Qdrant store with `BAAI/bge-base-en-v1.5` embeddings and insurer/policy metadata filtering.
- [x] **Sparse BM25 Search** ([`src/rag/retriever.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/retriever.py)): BM25Okapi integration for exact keyword matching of medical procedures and clause IDs.
- [x] **Reciprocal Rank Fusion (RRF)**: Merges dense vector hits and BM25 lexical rankings with $k=60$.
- [x] **Cross-Encoder Reranker** ([`src/rag/reranker.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/reranker.py)): Top 20 candidate chunks reranked using `ms-marco-MiniLM-L-6-v2`.
- [x] **LLM Query Rewriter** ([`src/rag/rewrite.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/rewrite.py)): Rewrites claim language into policy phrasing with persistent disk caching (`data/golden_set/rewrite_cache.json`).
- [x] **Empirical Retrieval Benchmark**: Full setup achieves **0.855 MRR** (+43.5% over dense baseline) and **92.9% Recall@3** on the 28 golden test questions.

### 3. Deterministic Financial Calculator
- [x] **Decimal Calculation Engine** ([`src/tools/calculator.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/tools/calculator.py)):
  - 100% Python `Decimal` logic—LLM never performs arithmetic.
  - Non-payable exclusions (consumables, non-medical charges per IRDAI list).
  - Room-rent daily cap with automatic proportionate deduction on associated charges (surgeon, OT, nursing, fees).
  - Policy deductibles, co-payment percentages, sub-limits, and sum insured capping.
  - Completely eliminates financial leakage (**0.0% overpayment rate**).

### 4. Synthetic Ground-Truth Claim Dataset
- [x] **30 Synthetic Claims Across 11 Scenarios** ([`synth/`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/synth/)):
  - Clean approvals (8), room-cap & proportionate deductions (4), non-payables (2), sum insured caps (2), 30-day initial waiting period rejections (2), specified disease 24-month exclusions (4), pre-existing disease (PED) rejections (2), multi-hop policies (2), missing documents (2), billing total mismatches (2).
  - Ground truth computed by reference rules with expected decision, payable amount, and cited clause IDs.
  - Ground truth validation ([`synth/validate_ground_truth.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/synth/validate_ground_truth.py)): verifies all cited clauses exist in indexed policy chunks.
- [x] **208 Realistic Rendered PDFs** ([`synth/render.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/synth/render.py)):
  - Generated via ReportLab: claim form, policy schedule, discharge summary, hospital bill in 4 distinct hospital layouts, photo ID proof.
  - ~33% degraded with simulated skew, contrast variations, and scanning artifacts.

### 5. Baseline Completion ("Before" Row)
- [x] **Single-Model Rerun Completed**: Replaced the older mixed-model predictions with a clean single-model run across all 30 claims ([`eval/results/naive_baseline_predictions.json`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/eval/results/naive_baseline_predictions.json)).
- [x] **Settled Citation & Diagnostic Question**:
  - Diagnosed claim C026 and confirmed that naive prompt retrieval frequently misses waiting-period clauses.
  - Baseline metrics locked in: **43.3% decision accuracy, 38.0% payable exact match, 53.3% overpayment rate, 16.0% citation recall, 19.0% citation precision, 17.0% hallucinated citations**.

### 6. Structured Extraction & OCR Evaluation
- [x] **Pydantic Claim Schemas** ([`src/extraction/schemas.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/extraction/schemas.py)): `ExtractedClaim` and `BillItem` with automated coercion and validation.
- [x] **Extraction Evaluation Executed** ([`eval/extraction_eval.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/eval/extraction_eval.py)): Scored across all 30 claims, achieving 1.00 (100%) accuracy on patient details, dates, financial amounts, and bill items.
- [x] **OCR Enhancements Implemented**:
  - Upgraded OCR rendering to 300 DPI to eliminate digit confusion on small fonts.
  - Integrated RapidOCR and bounding-box row clustering (`rows_from_boxes`) to accurately parse multi-column tables.
  - Multimodal vision fallback (`fill_with_vision`) for scanned pages where schedule parameters are missed.
  - Self-correction prompt retry loop if JSON parsing fails.

### 7. Pre-Adjudication Validation Layer
- [x] **Zero-LLM Rule Checker** ([`src/validation/checks.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/validation/checks.py)):
  - Checks presence of required documents (`claim_form`, `hospital_bill`, `discharge_summary`, `id_proof`).
  - Reconciles totals: $\sum(\text{items}) == \text{bill total} == \text{claimed total}$.
  - Validates date chronology: admission $\le$ discharge, policy start $\le$ admission.
  - Flags stay length vs room days charged discrepancies.
- [x] **Short-Circuit to `needs_review`**: Directly routes invalid claims to `decision: "needs_review"` before executing any LLM or policy reading calls.

### 8. Core Adjudication Pipeline & Anti-Hallucination Guard
- [x] **Topic-Targeted Policy Reader** ([`src/adjudication/reader.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/adjudication/reader.py)): Queries policy candidates grouped by 9 specific adjudication topics.
- [x] **Anti-Hallucination Citation Filter**: Programmatically discards any clause ID cited by the LLM that was not present in the retrieved candidates (achieving 0.0% hallucinated citations).
- [x] **Decision Engine** ([`src/adjudication/engine.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/adjudication/engine.py)): Evaluates waiting periods, pre-existing conditions, room modifications, and feeds clean terms to the calculator.

### 9. Test Suite
- [x] **122 Passing Tests**: Full coverage across retrieval, chunking, calculator math, Pydantic extraction, document rendering, validation, and waiting-period handling.

---

## ⏳ What’s Left (Active Backlog)

The remaining work is divided into 6 clear tasks:

### Task 1: Complete Policy Rule Set Mappings
*Current state*: [`synth/rules.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/synth/rules.py#L41-L55) only maps `niva_aspire` and `hdfc_optima_secure_current`.
- [ ] **Map Care Health (`care_supreme_current`)**: Define clause IDs for 30-day initial waiting period, PED waiting period, specified diseases, room rent cap, and non-payable expenses.
- [ ] **Map HDFC Optima Restore (`hdfc_optima_restore_current`)**: Map clause IDs for Restore terms and exclusions.
- [ ] **Map Star Health (`star_comprehensive_current`)**: Map clause IDs for Star Comprehensive definitions and exclusion sections.
- [ ] **Expand Synthetic Claims**: Add synthetic test claims for Care, HDFC Restore, and Star to verify cross-insurer coverage.

### Task 2: Verifier Agent & Human-in-the-Loop Workflow
*Current state*: Basic citation filter exists in `reader.py` and rule flags feed `needs_review`, but no dedicated Verifier LLM agent exists (`src/agents/` is empty).
- [ ] **Build Verifier Agent (`src/agents/verifier.py`)**: Adversarially reviews the Adjudicator's decisions:
  - Cross-checks whether diagnosed illness falls under undisclosed pre-existing conditions.
  - Validates if proportionate deductions were applied when room rent was breached.
  - Verifies that cited clauses support the specific deduction reason.
- [ ] **Human-in-the-Loop (HITL) Review Flow**: For claims flagged with `needs_review` or where Verifier confidence is below threshold, generate a structured adjuster audit packet for manual sign-off.

### Task 3: LangGraph Orchestration Graph
*Current state*: [`src/graph/`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/graph/) contains only an empty `__init__.py`.
- [ ] **Define State Schema (`src/graph/state.py`)**: Track claim documents, extracted claim, validation report, retrieved clauses, adjudicator findings, verifier critique, and final decision.
- [ ] **Build Workflow Nodes & Conditional Edges (`src/graph/workflow.py`)**:
  - `Node: Ingestion & OCR`
  - `Node: Structured Extraction`
  - `Conditional Edge: Validation Check` $\to$ if invalid, route to `Node: Human Review Queue`.
  - `Node: Clause Retrieval (Hybrid RAG)`
  - `Node: Adjudicator`
  - `Node: Verifier (Critique Loop)` $\to$ if critique fails, retry Adjudicator (max 2 iterations).
  - `Node: Deterministic Calculator`
- [ ] **State Checkpointer**: Add LangGraph Memory/SQLite checkpointer for persisting claim states during human review.

### Task 4: Application Layer & Deployment
*Current state*: `src/api/`, `src/ui/`, `src/security/` are empty; `Dockerfile` does not exist.
- [ ] **FastAPI Backend (`src/api/main.py`)**:
  - `POST /claims/upload`: Multi-part PDF upload and claim creation.
  - `POST /claims/{claim_id}/adjudicate`: Execute the adjudication graph.
  - `GET /claims/{claim_id}`: Fetch decision, itemized deductions, and cited clauses.
  - `GET /rag/search`: Search policy clauses.
- [ ] **Streamlit UI (`src/ui/app.py`)**:
  - *Claimant View*: Upload claim PDFs and view instant submission status.
  - *Adjuster Cockpit*: Side-by-side view of bill vs extracted items, itemized deduction math, and clickable legal clause citations.
- [ ] **Security & Guardrails (`src/security/`)**:
  - Prompt injection detection for uploaded PDF text.
  - PII masking (Aadhaar, PAN, phone numbers) before sending data to LLM APIs.
- [ ] **Production Dockerfile & Compose**: Write a multi-stage `Dockerfile` with Tesseract, Poppler, and Python 3.11, wired to `docker-compose.yml`.
- [ ] **Langfuse Tracing**: Integrate Langfuse callback handler for observability into LLM latency, token cost, and retrieval traces.

### Task 5: Final Evaluation, RAGAS/DeepEval & 10 Fresh Held-Out Questions
*Current state*: Baseline and full pipeline ablation tables are complete, but RAGAS/DeepEval and fresh held-out questions are not yet integrated.
- [ ] **Curate 10 Fresh Held-Out Retrieval Questions**: Create 10 completely unseen claim questions to evaluate retrieval generalization without prompt-tuning leakage.
- [ ] **Integrate RAGAS / DeepEval**: Add automated evaluation for faithfulness, answer relevancy, and context precision.
- [ ] **Produce Unified End-to-End Evaluation Report**: Consolidate baseline $\to$ extraction $\to$ hybrid RAG $\to$ calculator $\to$ full pipeline metrics.

### Task 6: Document Limitations in README
*Current state*: `README.md` exists with architecture and failure modes, but lacks a dedicated limitations section.
- [ ] **Add Dedicated Limitations Section in [`README.md`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/README.md)** covering:
  1. *Uniform Synthetic Bills*: Generated from ReportLab templates; real-world hospital bills feature non-standard handwriting and unformatted thermal receipts.
  2. *Simplified Proportionate-Deduction and Consumables Rules*: Policy rules currently model category-level consumable exclusions rather than line-by-line IRDAI List I-IV item checks.
  3. *Flattened Tables in Policy Text*: Multi-column policy schedule tables are flattened to plain text by the chunker.

---

## 📊 Summary Comparison: Roadmap Note vs. Current State

| Item from Note | Earlier Note Status | Current Reality | Notes / File Reference |
|---|:---:|:---:|---|
| **6 Policy wordings, cleaning & chunking** | Done | **DONE ✅** | [`src/rag/chunker.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/chunker.py) |
| **Hybrid RAG (Dense + BM25 + Rerank + Rewrite)** | Done | **DONE ✅** | 0.855 MRR, [`src/rag/retriever.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/rag/retriever.py) |
| **Deterministic Calculator** | Done | **DONE ✅** | 0.0% overpay, [`src/tools/calculator.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/tools/calculator.py) |
| **30 Synthetic Claims & 208 PDFs** | Done | **DONE ✅** | [`synth/generate.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/synth/generate.py), ReportLab |
| **Finish Baseline on single model & settle citations** | Left | **DONE ✅** | All 30 claims rerun; 53.3% overpay baseline recorded |
| **Run extraction eval & fix OCR/dates/layouts** | Left | **DONE ✅** | 300 DPI, RapidOCR, vision fallback; scored 100% on key scalars |
| **Build validation layer without LLM** | Left | **DONE ✅** | [`src/validation/checks.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/validation/checks.py) feeds `needs_review` |
| **Adjudication pipeline & calculator integration** | Left | **DONE ✅** | [`src/adjudication/pipeline.py`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/src/adjudication/pipeline.py) |
| **Map rules for Care, HDFC Restore & Star** | Left | **LEFT ❌** | Only Niva and HDFC Secure are currently mapped in `rules.py` |
| **Verifier agent & Human-in-the-Loop step** | Left | **LEFT ❌** | `src/agents/` is empty; HITL workflow not built |
| **LangGraph orchestration graph** | Left | **LEFT ❌** | `src/graph/` is empty |
| **App layer (FastAPI, Streamlit, Docker, Langfuse)** | Left | **LEFT ❌** | `src/api/`, `src/ui/` are empty; no Dockerfile |
| **RAGAS/DeepEval + 10 fresh held-out questions** | Left | **LEFT ❌** | Custom ablation tables done; RAGAS and fresh questions pending |
| **README Limitations section** | Left | **LEFT ❌** | README exists, but specific limitations not yet written |

