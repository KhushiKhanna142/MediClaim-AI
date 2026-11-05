# MediClaim-AI

Automated health insurance claim adjudication and verification engine powered by multimodal LLMs, LangGraph, and hybrid RAG.

---

## 📌 Repository Structure

```text
├── README.md               # problem, architecture, ablation table, failure modes, trade-offs
├── docker-compose.yml
├── data/
│   ├── policies/           # raw policy PDFs (check redistribution terms)
│   ├── regulations/        # IRDAI circulars
│   ├── synthetic_claims/   # PDFs + ground-truth JSON
│   └── golden_set/         # frozen 50 claims + retrieval questions
├── src/
│   ├── ingestion/          # loaders, page classifier, OCR router
│   ├── extraction/         # schemas, extraction agent, table parsers
│   ├── validation/         # rule-based validators
│   ├── rag/                # chunkers, indexer, hybrid retriever, reranker, query rewrite
│   ├── agents/             # adjudicator, verifier
│   ├── tools/              # calculator, icd lookup, policy-active check (also exposed via MCP)
│   ├── graph/              # LangGraph state, nodes, edges, checkpointer
│   ├── security/           # injection detection, PII redaction
│   ├── api/                # FastAPI app
│   └── ui/                 # Streamlit claimant + reviewer
├── synth/                  # data generator, renderers, degradation scripts
├── eval/                   # metrics, RAGAS/DeepEval runners, ablation runner
├── experiments/            # one notebook/script per failure mode
├── tests/                  # unit + adversarial tests
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

1. **Ingestion & Classification**: Multimodal loaders and OCR router process scanned bills, handwritten discharge notes, and hospital ledgers.
2. **Information Extraction**: Pydantic schemas enforce deterministic structured data extraction across diagnosis codes (ICD-10), billed items, and claimant details.
3. **Security & Guardrails**: PII redaction and prompt-injection detection run prior to reasoning.
4. **Hybrid RAG & Regulatory Retrieval**: Hybrid retriever (BM25 + dense embeddings) and cross-encoder rerankers index policy wordings, terms, and IRDAI circulars.
5. **Agentic Adjudication via LangGraph**:
   - **Adjudicator Agent**: Matches claim items against policy allowances, waiting periods, room-rent sub-limits, and deductibles using deterministic calculator tools.
   - **Verifier Agent**: Adversarially reviews adjudication decisions for hallucinations, misapplied clauses, or regulatory breaches before final determination.
6. **Delivery**: FastAPI endpoints power backend integrations, while Streamlit interfaces serve claimant submission and reviewer dashboards.

---

## 🔬 Ablation Table

| Configuration / Pipeline Variant | Extraction Accuracy (F1) | Retrieval Precision@k | Adjudication Accuracy | Latency (p95) | Cost per Claim ($) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Baseline (Vanilla Prompting + Naive RAG) | - | - | - | - | - |
| + Document Structure & Table Parsing | - | - | - | - | - |
| + Hybrid Retrieval & Cross-Encoder Reranker | - | - | - | - | - |
| + Rule-based Deterministic Validation | - | - | - | - | - |
| + Dual-Agent LangGraph (Adjudicator + Verifier) | - | - | - | - | - |

---

## ⚠️ Failure Modes & Mitigations

1. **OCR / Table Parsing Errors in Scanned Bills**
   - *Mitigation*: Degradation testing in `synth/`, ensemble OCR routers, and table parsing fallbacks.
2. **Ambiguous Policy Exclusions & Subjective Clauses**
   - *Mitigation*: Query rewrite + hybrid retrieval with source clause citations; flagged for human reviewer if confidence score falls below threshold.
3. **Prompt Injection & Adversarial Document Uploads**
   - *Mitigation*: Dedicated security filter (`src/security/`) sanitizing input text and stripping embedded prompt injections from uploaded PDFs.
4. **Hallucinated Sub-limits or Math Errors**
   - *Mitigation*: Offloading all financial math to deterministic calculator tools (`src/tools/`) rather than relying on LLM arithmetic.

---

## ⚖️ Trade-offs

- **Single-Pass LLM vs. Multi-Agent Graph**: Multi-agent verification increases token cost and latency but drastically reduces false-positive claim denials and hallucinations.
- **Dense Retrieval vs. Hybrid (BM25 + Dense) Retrieval**: Hybrid retrieval requires higher indexing memory but is essential for matching exact clause numbers, IRDAI section codes, and medical terminology.
- **Full Automation vs. Human-in-the-Loop (HITL)**: Borderline claims or high-value claims route to the reviewer UI, trading immediate turnaround for regulatory compliance and risk control.

