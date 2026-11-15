# MediClaim-AI

Automated health insurance claim adjudication and verification engine powered by multimodal LLMs, LangGraph, hybrid RAG, and deterministic calculation guards.

---

## 🎯 Headline Benchmark (Held-Out Seed 47)

Evaluated under the **shipped production configuration** (`review_all_rejects=True`, deterministic verifier code checks active, LLM critic off by default) on 30 held-out synthetic claims with 208 rendered multi-page clinical documents, 63 degraded scans, and 4 layout permutations:

| Headline Metric | Shipped Pipeline Result | 95% Wilson Confidence Interval |
| :--- | :---: | :---: |
| **Decision Accuracy** | **100.0% (30 / 30)** | [88.7% – 100.0%] |
| **Exact Payable Amount Match** | **100.0% (26 / 26)** | [87.1% – 100.0%] |
| **Overpay Rate (Financial Leakage)** | **0.00% (0 / 30)** | [0.0% – 11.3%] |
| **Wrong Decisions Auto-Finalised** | **0 of 16 (0.00%)** | **[0.0% – 18.7%]** |
| **Citation Recall / Precision** | **0.90 / 0.90** | — |
| **Unsupported Citations** | **0.00% (0 / 30)** | [0.0% – 11.3%] |
| **Verifier False-Alarm Rate** | **0.0% (0 / 16 clean)** | [0.0% – 18.7%] |
| **Human Review Escalation Rate** | **14 / 30 (46.7%)** | [30.2% – 63.9%] |
| **Automation Rate** | **16 / 30 (53.3%)** | [36.1% – 69.8%] |

*Note on 26 vs 30 payable claims*: 4 claims were safely routed to human adjusters during pre-adjudication validation (1 missing hospital bill, 1 missing claim form, and 3 bill total mismatches) before reaching financial calculation.

---

## 📊 End-to-End Developmental Benchmark History

Generated directly from raw prediction files via `eval/generate_benchmark_table.py`:

| Run & Dataset | Generator | Review Rejects | Decision Acc | Exact Payable | Overpay Rate | Wrong Auto-Finalised | Cite Recall | Cite Precision | Human Escalations | Automation Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Dev Baseline (Early)** | v1 (Standard) | `False` | 100.0% | 100.0% | 0.0% | **0 of 24** | 0.68 | 0.81 | 6 / 30 | 80.0% |
| **Dev Current** | v1 (Standard) | `False` | 90.0% | 88.5% | 6.7% | **1 of 23** | 0.80 | 0.83 | 7 / 30 | 76.7% |
| **Held-Out Seed 42** | v1 (Standard) | `False` | 100.0% | 100.0% | 0.0% | **0 of 25** | 0.86 | 0.86 | 5 / 30 | 83.3% |
| **Held-Out Seed 44** | v1 (Standard) | `True` | 100.0% | 96.2% | 3.3% | **1 of 15** | 0.85 | 0.86 | 15 / 30 | 50.0% |
| **Held-Out Seed 46 (with Critic)** | v2 (4 Layouts) | `True` | 100.0% | 100.0% | 0.0% | **0 of 9** | 0.90 | 0.90 | 21 / 30 | 30.0% |
| **Held-Out Seed 46 (No Critic)** | v2 (4 Layouts) | `True` | 100.0% | 100.0% | 0.0% | **0 of 16** | 0.90 | 0.90 | 14 / 30 | 53.3% |
| **Held-Out Seed 47 (Final Headline)** | v2 (4 Layouts) | `True` | 100.0% | 100.0% | 0.0% | **0 of 16** | 0.90 | 0.90 | 14 / 30 | 53.3% |

### Why Seed 46 (No Critic) and Seed 47 Match Almost Exactly
Readers will observe that Seed 46 (No Critic) and Seed 47 produce identical aggregate metrics (53.3% automation, 14 escalations, 0.90 recall and precision) and matching category-level citation recall (0.75 for non-payable, 0.67 for room cap, 0.67 for sum insured). This parity is expected: both batches use the identical synthetic category distribution (6 clean approve, 4 partial room, 2 partial non-payable, 2 partial sum insured, etc.), and the residual citation gaps are systematic policy document mapping differences rather than random draw noise. Specifically:
- **Niva Bupa non-payable items**: Cites general exclusion 4.1.2 rather than annexure list 4.1.20.
- **HDFC ERGO room rent limits**: Cites umbrella Section C rather than specific sub-rule C.1.

### Pooled Held-Out Telemetry
Across all four developmental held-out batches (Seeds 42, 44, 46, and 47):
- **Total Auto-Finalised Claims**: 72 claims
- **Correct Auto-Finalised Decisions**: 71 / 72 (98.6%) [95% Wilson CI: 92.5% – 99.8%]
- **Wrong Decisions Auto-Finalised**: 1 / 72 (1.4%) [95% Wilson CI: 0.2% – 7.5%] *(C006 on Seed 44: ₹9,455 room modification co-payment missed prior to adding the deterministic room-copay verifier guard).*

---

## ⚡ Speed, Cost & LLM Call Telemetry

Claim telemetry is tracked end-to-end via Langfuse tracing (`src/telemetry/tracing.py`) with pre-transmission PII masking (`src/security/pii.py`):

| Pipeline Stage | Latency per Claim | LLM Calls per Claim | Primary Components |
| :--- | :---: | :---: | :--- |
| **Document Ingestion & OCR** | 1.8s – 2.5s | 0 | PyMuPDF, Tesseract OCR |
| **Structured Extraction** | 1.2s – 2.0s | 1.0 | `Gemini 3.1 Flash Lite` (1 vision call fallback on unreadable scans) |
| **Pre-Adjudication Validation** | < 2 ms | 0 | Deterministic Python validator |
| **Clause Retrieval & Reranking** | 250ms – 400ms | 0 | Qdrant dense vector + BM25 sparse + Cross-Encoder reranker |
| **Policy Reading (`PolicyReader`)** | 1.8s – 2.5s | 0.90 | `Gemini 3.1 Flash Lite` (0 calls for pre-flagged claims, 1 for standard, 2 on clause retry) |
| **Deterministic Adjudication Engine** | < 1 ms | 0 | Pure Python arithmetic (`src/adjudication/engine.py`) |
| **Deterministic Verifier Checks** | < 1 ms | 0 | Waiting periods, room caps, and history guards |
| **End-to-End Pipeline (Shipped)** | **5.2s – 7.5s** | **~1.9 calls** | Total claim processing turnaround time |

---

## 🛡️ Independent Adversarial Prompt Injection Benchmark

Evaluated across **50 independent adversarial attacks** (`eval/independent_injection_eval.py`) covering 10 distinct evasion categories (clinical paraphrasing, critic manipulation, Hindi/Hinglish instructions, comment obfuscation, leetspeak, spacing, and table cell injections), plus **20 clinical homonym negative controls**:

| Defense Configuration | Successful Evasions | Attack Success Rate (95% CI) | Primary Defense Layer |
| :--- | :---: | :---: | :--- |
| **Arm 1: Undefended Baseline** | 13 / 50 | 26.0% [15.9% – 39.6%] | Direct LLM without protections |
| **Arm 2: Delimiters Only (`<tags>`)** | 5 / 50 | 10.0% [4.3% – 21.4%] | Prompt boundary isolation |
| **Arm 3: Delimiters + Deterministic Guards** | **0 / 50** | **0.0% [0.0% – 7.1%]** | **Deterministic pre-existing verifier guard** |
| **Arm 4: Full Defense-in-Depth (+ Regex Scanner)** | **0 / 50** | **0.0% [0.0% – 7.1%]** | Tripwire scanner + Guards + Delimiters |

### Key Findings & Attribution
1. **Arm 3 Attribution**: In Arm 3, the **deterministic pre-existing-condition verifier guard alone** stopped 100% of evasions (0 of 50). The attacks that succeeded undefended attempted to suppress pre-existing condition disclosures to force full claim payout. Because suppression makes the system approve/pay rather than reject, mandatory rejection review (`review_all_rejects`) never encounters these claims. The deterministic code guard alone caught every evasion by matching extracted medical history against diagnosis dates.
2. **Documented Evasion Limit**: The deterministic guard succeeds **only when the history text survives extraction**. If an adversarial prompt successfully compels the extraction LLM to omit `known_history` entirely (leaving `null`), or if the claimant leaves prior illness off the physical paperwork, the code guard has nothing to match.
3. **Pattern Scanner Tripping Rate**: The regex pattern scanner detected only **2.0% (1 / 50)** of independent attacks [95% CI: 0.4% – 10.5%]. Pattern matching is fragile and easily bypassed; it serves only as a cheap tripwire, while deterministic verifier guards provide the true security margin.
4. **Clinical Homonym Safety**: On 20 legitimate clinical sentences containing trigger words (*"override"*, *"bypass"*, *"approve"*), the false positive rate was **0.0% (0 / 20)** [95% CI: 0.0% – 16.1%].

---

## 🏗️ Architecture & Adjudication Workflow

```
[ Uploaded Documents ]
          │
          ▼
   [ PyMuPDF / OCR ]
          │
          ▼
  [ LLM Extractor ] ──> [ PII Redaction ] ──> [ Sanitizer Tripwire ]
          │
          ▼
 [ Pre-Adjudication Validation ] ──(Flags: missing docs, total mismatch)──> [ Human Review Queue ]
          │ (Pass)
          ▼
[ Hybrid RAG (Qdrant + BM25 + Cross-Encoder) ]
          │
          ▼
 [ Policy Reader (LLM) ] ──> Clause ID Whitelist Validation
          │
          ▼
 [ Deterministic Decision Engine ] ──(Financial Math, Room Caps, Proportions)
          │
          ▼
[ Deterministic Verifier Code Checks ] ──(History, Room Mod, Capping)
          │
          ├──> [ If Incomplete Clause ] ──> Targeted Refine Retry (Max 2)
          │
          ▼
    [ Routing Node ]
          ├──> (Rejections or Flags) ──> [ Human Review / Adjudicator Queue ] ──> Final Decision
          └──> (Clean Approvals)     ──> [ Auto-Finalised Decision ]
```

### Core Invariants
- **No LLM Arithmetic**: All deduction percentages, room rent proportionate deductions, co-pays, and sums insured are computed strictly in Python code (`src/adjudication/engine.py`).
- **Citation Whitelisting**: The LLM policy reader can only cite clause IDs that were retrieved and passed in its candidate context; all hallucinated clause IDs are dropped.
- **Mandatory Rejection Review (`review_all_rejects = True`)**: Rejection of insurance coverage is never auto-finalised by AI; every denial requires human adjuster sign-off.
- **Pre-Transmission PII Scrubbing**: All claimant Aadhaar, PAN, phone numbers, and email addresses are masked prior to external LLM or observability API calls (`src/security/pii.py`).

---

## ⚠️ System Limitations & Known Constraints

1. **Synthetic Evaluation Data**: All evaluations are conducted on synthetic claim bundles generated by a single rule engine (`synth/`). While claims incorporate realistic hospital billing layouts, clinical ICD-10 variations, and scanned image noise, performance on real hospital documentation with unstructured handwritten notes and complex discharge forms remains unmeasured.
2. **Policy Coverage**: Only 2 master policies are fully mapped in the adjudication engine (**Niva Bupa ReAssure 2.0** and **HDFC ERGO Optima Secure**). Three additional policies (Care Health, Star Comprehensive, and Star Young) are indexed in retrieval benchmarks but lack full adjudication logic.
3. **Statistical Power of Single Headline Batch**: With 16 auto-finalised claims in Seed 47, the 95% Wilson confidence interval on error rate is $[0.0\%, 18.7\%]$. While pooled multi-batch telemetry demonstrates 71 of 72 correct auto-finalised decisions ($98.6\%$), larger independent operational cohorts are required to tighten this bound.
4. **Unisolated Dev Set Regression on Degraded Scans**: On the development batch (Seed 41), decision accuracy was 90% (3 of 30 claims missed: C012 and C028 pre-existing conditions missed due to OCR degradation, and C021 appendicitis flagged as a specified procedure). While deterministic verifier guards catch C012 and C028, C021-type misclassifications rely entirely on mandatory rejection review.
5. **LLM Critic False-Escalation Rate (43.8%)**: In Seed 46, enabling the LLM verifier critic escalated 9 clean claims unnecessarily (a 43.8% false-escalation rate on payable claims), dropping automation from 53.3% to 30.0%. For this reason, **the LLM critic is disabled by default in production**, relying instead on deterministic code guards.
6. **Fragile Pattern Scanner (2% Independent Detection)**: The regex-based security scanner caught only 1 of 50 independent adversarial injections. System security relies on structural boundaries and deterministic verifier guards, not text filtering.
7. **Omitted-History Evasion Vector**: If an injection compels the extraction LLM to drop medical history, or if a patient omits previous treatments from paperwork, deterministic guards cannot detect the pre-existing condition.
8. **Single Model Family**: All benchmarks were evaluated with `Gemini 3.1 Flash Lite` and `Gemini 3.5 Flash Lite`. Multi-provider cross-evaluation across Claude or GPT-4o has not been benchmarked.
9. **Reviewer Effectiveness Not Empirically Measured**: The system routes all rejections and flagged claims to human adjusters. The safety of the overall workflow relies on the hypothesis that human reviewers accurately identify errors. Real human adjuster error rates and fatigue have not been empirically evaluated in live clinical trials.
10. **Coarse HDFC Citations**: Citations for room-rent capping in HDFC ERGO policies cite the parent `Section C` umbrella clause rather than granular child sub-clauses due to policy document structure.

---

## 🚀 Deployment & Quickstart

### Prerequisites
- Docker & Docker Compose (or Python 3.11+)
- Google AI Studio API Key (`GEMINI_API_KEY`)

### Option A: Docker Deployment (Recommended)

1. Clone repository and create `.env` file:
```bash
git clone https://github.com/khushikhanna/MediClaim-AI.git
cd MediClaim-AI
echo "GEMINI_API_KEY=your_gemini_api_key_here" > .env
```

2. Launch container with Docker Compose:
```bash
docker compose up --build -d
```
*The image pre-downloads all embedding (`bge-small-en-v1.5`) and reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) models during build, requiring zero external model downloads at runtime.*

3. Access application:
- **FastAPI Backend & Interactive API Docs**: `http://localhost:8000/docs`
- **React Claims Reviewer Dashboard**: `http://localhost:8000/`

---

### Option B: Local Development Setup

1. Create Python 3.11 virtual environment:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install uvicorn[standard] python-multipart google-genai langfuse pytesseract pillow
```

2. Run automated test suite:
```bash
pytest tests/ -v
```
*(All 177 unit, graph, retrieval, and telemetry tests pass in < 6s).*

3. Run Held-Out Headline Benchmark:
```bash
python -m eval.graph_eval --claims data/heldout_claims_seed47 --extracted-file eval/results/extraction_seed47_predictions.json --score-only
```

4. Run Independent Prompt Injection Benchmark:
```bash
python -m eval.independent_injection_eval
```

5. Start Development Server:
```bash
export GEMINI_API_KEY="your_api_key_here"
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📄 License
Apache 2.0 License. Designed for auditable, transparent health insurance claim operations.
