# Sample Synthetic Claim Documents for Manual Testing

These 4 documents have been placed in the folder [`sample_claim_documents/`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/sample_claim_documents/) so you can easily upload them in the UI's manual submission form.

### Claim Scenario Details
- **Patient**: Matthew Rana (Age 55, Female)
- **Insurer / Policy**: Niva Bupa (*Aspire*)
- **Treatment / Diagnosis**: Inguinal Hernia Repair (Illness)
- **Hospitalization Dates**: 19 Feb 2025 to 21 Feb 2025 (2 days)
- **Room Type**: Standard Single AC Room (₹4,700/day)
- **Claimed / Billed Amount**: ₹82,800
- **Expected Adjudication Outcome**: **Approved (₹82,800)** (Standard clean approval within sum insured, past waiting period, no non-payable exclusions).

---

### Files to Upload

| Slot in UI | File Path | Description |
| :--- | :--- | :--- |
| **1. Claim Form (Part A/B)** | [`sample_claim_documents/claim_form.pdf`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/sample_claim_documents/claim_form.pdf) | Signed claim reimbursement form with patient details, policy number, and diagnosis. |
| **2. Itemized Hospital Bill** | [`sample_claim_documents/hospital_bill.pdf`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/sample_claim_documents/hospital_bill.pdf) | Hospital invoice breaking down room, surgeon, OT, nursing, medicine, and implant charges totaling ₹82,800. |
| **3. Discharge Summary** | [`sample_claim_documents/discharge_summary.pdf`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/sample_claim_documents/discharge_summary.pdf) | Clinical discharge summary detailing procedure, admission/discharge dates, and absence of prior history. |
| **4. Government ID Proof** | [`sample_claim_documents/id_proof.pdf`](file:///Users/khushikhanna/Desktop/Projects/MediClaim-AI/sample_claim_documents/id_proof.pdf) | Government ID card with PII identifiers (Aadhaar / PAN). |

---

### How to Test in the UI

1. Open the **Submit a Claim** view in the UI.
2. Under **Policy Product**, select **Niva Bupa — Aspire**.
3. In the **Upload Claim Documents (Manual Submission)** section:
   - Drag & drop or browse to select each corresponding PDF from `sample_claim_documents/`.
4. Once all 4 slots show green checkmarks, click **"Submit Claim for Adjudication"**.
5. The UI will automatically run the claim through the extraction, security scan, pre-adjudication validation, policy retrieval, deterministic calculator, and verifier.

