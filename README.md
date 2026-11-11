# MediClaim-AI

Automated health insurance claim adjudication and verification engine powered by multimodal LLMs, LangGraph, and hybrid RAG.

---

## 📌 Repository Structure

```text
├── README.md               # problem, architecture, ablation table, failure modes, trade-offs
├── docker-compose.yml
├── data/
│   ├── policies/           # raw policy PDFs (Care, HDFC ERGO, Niva Bupa, Star Health)
│   ├── regulations/        # IRDAI master circulars, regulations & claim forms
│   ├── synthetic_claims/   # 30 grounded claims (PDFs + ground-truth JSON + manifest)
│   ├── processed/          # cleaned texts and hierarchical clause chunks (JSONL)
│   ├── qdrant/             # local vector store indexing policy chunks
│   └── golden_set/         # frozen benchmark questions & query rewrite cache
├── src/
│   ├── ingestion/          # loaders, bilingual text stripper, clean text normalizer
│   ├── extraction/         # schemas, extraction agent, table parsers
│   ├── validation/         # rule-based validators
│   ├── rag/                # chunker, indexer, hybrid retriever, reranker, query rewrite
│   ├── agents/             # adjudicator, verifier
│   ├── tools/              # deterministic calculator (room rent, copay, non-medical)
│   ├── graph/              # LangGraph state, nodes, edges, checkpointer
│   ├── security/           # injection detection, PII redaction
│   ├── api/                # FastAPI app
│   └── ui/                 # Streamlit claimant + reviewer
├── synth/                  # synthetic claim data generator, rule engine & ground truth
├── eval/                   # retrieval benchmark & ablation runners
├── experiments/            # one notebook/script per failure mode
├── tests/                  # unit, retrieval, and synthetic test suites (88 tests passing)
└── docs/                   # architecture diagram, cost analysis, decision log
```

---

## 🚨 Problem

Health insurance claims processing suffers from:
- **High Latency & Manual Overhead**: Claim review cycles take days to weeks, requiring human adjudicators to cross-reference multi-page hospital invoices, discharge summaries, and complex policy terms.
- **Inconsistent Decision Making**: Complex exclusions, copay clauses, room-rent capping, and IRDAI circulars lead to erratic claim approval/deduction outcomes.
- **Fraud, Waste, and Abuse (FWA)**: Inconsistencies between diagnosis and line-item billing, manipulated invoices, and policy-active status discrepancies often slip through manual reviews.

MediClaim-AI automates end-to-end claim adjudication with full auditability, citation-backed decision rationales, and human-in-the-loop review.

---

## 🏗️ Architecture

1. **Ingestion & Classification**: Multimodal loaders and OCR router process scanned bills, handwritten discharge notes, and hospital ledgers. De-noising strips bilingual Hindi/English boilerplate from IRDAI circulars.
2. **Information Extraction**: Pydantic schemas enforce deterministic structured data extraction across diagnosis codes (ICD-10), billed items, and claimant details.
3. **Security & Guardrails**: PII redaction and prompt-injection detection run prior to reasoning.
4. **Hybrid RAG & Regulatory Retrieval**:
   - **Clause-Aware Hierarchical Chunking**: Parent chunks preserve full legal context, clause IDs (`4.1(a)`, `2.13`), and active dates; child chunks power precision search.
   - **Hybrid Retrieval**: Combines Reciprocal Rank Fusion of BAAI/BGE dense embeddings in Qdrant with BM25 sparse keyword matching.
   - **Cross-Encoder Reranker**: Re-ranks top candidate clauses via `ms-marco-MiniLM-L-6-v2`.
   - **LLM Query Rewriter**: Translates patient/claimant symptoms into exact policy phrasing with disk-backed caching.
5. **Deterministic Adjudication Engine**:
   - Offloads financial deductions (room-rent proportionate deduction, deductibles, co-pays, and IRDAI non-payable items) to deterministic calculation tools rather than relying on LLM arithmetic.
6. **Agentic Adjudication via LangGraph**:
   - **Adjudicator Agent**: Matches claim items against policy allowances and waiting periods.
   - **Verifier Agent**: Adversarially reviews adjudication decisions for hallucinations, misapplied clauses, or regulatory breaches before final determination.
7. **Delivery**: FastAPI endpoints power backend integrations, while Streamlit interfaces serve claimant submission and reviewer dashboards.

---

## 🔬 Measured Retrieval Ablation Table

Evaluated on the 28-question frozen golden benchmark (`data/golden_set/retrieval_questions.jsonl`):

| Pipeline Configuration | Recall@1 | Recall@3 | Recall@5 | MRR | Relative Gain |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Dense Vector Search (Baseline)** | 0.46 | 0.71 | 0.79 | 0.596 | Baseline |
| **2. BM25 Lexical Search** | 0.64 | 0.68 | 0.75 | 0.681 | +14.2% MRR |
| **3. Hybrid Search (BM25 + Dense RRF)** | 0.50 | 0.82 | 0.82 | 0.640 | +7.4% MRR |
| **4. Hybrid + Cross-Encoder Reranker** | 0.68 | 0.82 | 0.86 | 0.767 | +28.7% MRR |
| **5. Hybrid + Query Rewriter (`hybrid_rw`)** | 0.71 | 0.86 | 0.89 | 0.788 | +32.2% MRR |
| **6. Full Pipeline (`hybrid_rerank_rw`)** | **0.79** | **0.93** | **0.93** | **0.855** | **+43.5% MRR** |

---

## 📊 End-to-End Adjudication Benchmark

Evaluated on the full 30-claim synthetic golden benchmark (`data/synthetic_claims/`):

| Pipeline Architecture | Decision Acc | Payable Exact | Overpay Rate ⚠️ | Mean Error % | Citation Recall | Citation Precision |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Naive Direct LLM Baseline** | 43.3% | 38.0% | **53.3%** | 47.8% | 16.0% | 19.0% |
| **2. MediClaim Pipeline (OCR Extracted)** | **73.3%** | **81.0%** | **0.0%** | **17.3%** | **47.0%** | **49.0%** |
| **3. Oracle Pipeline (Ground-Truth Input)** | **100.0%** | **100.0%** | **0.0%** | **0.0%** | **75.0%** | **68.0%** |

> **Key Finding**: Direct LLM prompting suffers from a **53.3% overpayment rate** due to hallucinated coverage and missed policy exclusions. MediClaim-AI's hybrid clause retrieval and deterministic calculator engine (`src/tools/calculator.py`) **completely eliminates financial leakage (0.0% overpay rate)** while boosting payable amount accuracy from 38% to 81%.

---

## 🧪 Synthetic Ground-Truth Dataset (`synth/`)

Generated a 30-claim golden set (`data/synthetic_claims/manifest.json`) across 11 realistic adjudication scenarios with ground-truth decision outputs:
- **Clean Approvals (8 claims)**: Routine admissions meeting full policy waiting periods.
- **Partial Deductions (8 claims)**: Room-rent caps, proportionate deductions, IRDAI non-payable deductions, and sum insured caps.
- **Rejections (10 claims)**: 30-day initial waiting period violations, specified 24-month illness exclusions (cataract, hernia), and undisclosed pre-existing diseases (PED).
- **Audit & Review Required (4 claims)**: Missing mandatory bills, document tampering, and billing/diagnosis mismatches.

---

## ⚠️ Failure Modes & Mitigations

1. **OCR / Table Parsing Errors in Scanned Bills**
   - *Mitigation*: Degradation testing in `synth/`, ensemble OCR routers, and table parsing fallbacks.
2. **Ambiguous Policy Exclusions & Subjective Clauses**
   - *Mitigation*: Query rewrite + hybrid retrieval with source clause citations; flagged for human reviewer if confidence score falls below threshold.
3. **Prompt Injection & Adversarial Document Uploads**
   - *Mitigation*: Dedicated security filter (`src/security/`) sanitizing input text and stripping embedded prompt injections from uploaded PDFs.
4. **Hallucinated Sub-limits or Math Errors**
   - *Mitigation*: Offloading all financial math to deterministic calculator tools (`src/tools/calculator.py`).

---

## 🚀 Quickstart

### 1. Environment Setup
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Run Test Suite
```bash
python -m pytest -q tests/
```
*(All 114 unit and integration tests passing)*

### 3. Run Retrieval Benchmark & Ablation
```bash
set -a; source .env; set +a
python -m eval.retrieval_eval --questions data/golden_set/retrieval_questions.jsonl --rewrite
```

### 4. Generate Synthetic Ground-Truth Claims
```bash
python -m synth.generate
```
