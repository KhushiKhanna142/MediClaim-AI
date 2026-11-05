from src.rag.chunker import chunk_policy, clause_id, split_star_definitions, strip_headers

CARE = dict(policy_id="care", insurer="Care Health Insurance", product="Care Supreme", uin="X", status="current",
            effective_from=None, effective_to=None, source_type="insurer_policy")
STAR = {**CARE, "policy_id": "star", "insurer": "Star Health and Allied Insurance", "product": "Star Comprehensive"}
HDFC_OLD = {**CARE, "policy_id": "hdfc_old", "insurer": "HDFC ERGO", "product": "Optima Restore", "doc_ref": "CIS/Ver -1 NOV2021"}


def P(*texts, page=1):
    return [{"page": page, "text": t} for t in texts]


def test_clause_ids():
    assert clause_id("2.1.17. Hospital means any institution", "Care") == "2.1.17"
    assert clause_id("13. Automatic Restoration of Sum Insured: There shall", "Star") == "13"
    assert clause_id("Def. 18. Hospital means", "HDFC ERGO") == "Def.18"
    assert clause_id("Def.27. Medical Practitioner means", "HDFC ERGO") == "Def.27"
    assert clause_id("SECTION B. BENEFITS", "HDFC ERGO") == "Section B"
    assert clause_id("65 Section Plans Optima", "HDFC ERGO") is None      # page number residue, not a clause
    assert clause_id("a. Has qualified nursing staff", "Care") is None
    assert clause_id("Accident: An Accident means a sudden", "Star Health") == "Def:Accident"
    assert clause_id("Note: this applies to", "Star Health") is None


def test_lettered_items_stay_in_parent():
    recs = chunk_policy(P("2.1.17. Hospital means any institution established for inpatient care",
                          "a. Has qualified nursing staff under its employment round the clock;",
                          "b. Has at least 10 in-patient beds in towns having a population of less than 10,00,000"), CARE)
    parents = [r for r in recs if r["type"] == "parent"]
    assert len(parents) == 1 and parents[0]["clause_id"] == "2.1.17" and "10 in-patient beds" in parents[0]["text"]


def test_leaked_hdfc_header_removed():
    t = ("800 per day max upto 4800 HDFC ERGO General Insurance Company Limited. IRDAI Reg. No.146 CIN: U66030MH2007PLC177117. "
         "Registered & Corporate Office: 6th Floor, Leela Business Park, Andheri-Kurla Road, Andheri (East), Mumbai – 400 059. "
         "UIN: my: Optima Secure - HDFHLIP26058V082526 65 Section Plans")
    out = strip_headers(t)
    assert "Leela" not in out and "HDFHLIP" not in out and out.startswith("800 per day max upto 4800")


def test_star_definitions_split():
    para = ("Accident: An Accident means a sudden, unforeseen event. Any one Illness: Any one Illness means a continuous "
            "period of illness. Note: this is not a definition and stays attached.")
    parts = split_star_definitions(para)
    assert len(parts) == 2 and parts[1].startswith("Any one Illness:") and parts[1].endswith("attached.")


def test_old_hdfc_cis_pages_skipped():
    paras = [{"page": 1, "text": "Product Name Optima Restore What am I covered for: In-patient treatment table text here"},
             {"page": 2, "text": "How to Claim Kindly contact Us 48 hrs prior for planned hospitalisation to the toll free"},
             {"page": 3, "text": "SECTION A. DEFINITIONS: OTHER IMPORTANT TERMS YOU SHOULD KNOW"},
             {"page": 3, "text": "Def. 1. Accident means a sudden unforeseen and involuntary event caused by external means"}]
    recs = chunk_policy(paras, HDFC_OLD)
    assert all(r["page_start"] >= 3 for r in recs)


def test_children_capped_and_linked_to_parent():
    long = "2.2. Waiting periods " + " ".join(f"Sentence number {i} about waiting periods applies." for i in range(60))
    recs = chunk_policy(P(long), CARE)
    kids = [r for r in recs if r["type"] == "child"]
    assert len(kids) > 1 and all(len(k["text"]) <= 900 for k in kids)
    assert all(k["parent_id"] == "care::2.2" for k in kids)
    assert all(k["insurer"] == "Care Health Insurance" and k["uin"] == "X" for k in recs)


def test_duplicate_clause_ids_get_unique_chunk_ids():
    recs = chunk_policy(P("1. First clause text that is long enough to keep", "1. Another clause also long enough to keep"), CARE)
    ids = [r["chunk_id"] for r in recs if r["type"] == "parent"]
    assert len(set(ids)) == 2


from src.rag.chunker import is_heading, skip_toc_pages, split_parent


def test_headings_real_vs_fake():
    assert is_heading("I - DEFINITIONS")
    assert is_heading("SECTION B. BENEFITS")
    assert not is_heading("2.1.24. Maternity expenses shall include")
    assert not is_heading("Pre-Existing Disease: Pre-Existing Disease means any condition")


def test_numbered_heading_needs_children():
    from src.rag.chunker import heading_kind
    assert heading_kind("2. Definitions", "2", "2.1") == "major"
    assert heading_kind("2.1. Standard Definitions:", "2.1", "2.1.1") == "sub"
    assert heading_kind("1. Travel Expenses", "1", None) is None            # HDFC list item
    assert heading_kind("13. Automatic Restoration of Sum Insured", "13", "14") is None


def test_section_does_not_go_stale_after_new_major_heading():
    paras = P("SECTION B. BENEFITS", "1. In-patient Benefits covered when an insured suffers an accident or illness",
              "2. Additional Benefits covered under the policy when mentioned in schedule",
              "SECTION C. WAITING PERIOD AND EXCLUSIONS",
              "1. Pre-existing diseases shall be covered after a waiting period of 36 months of continuous coverage")
    recs = chunk_policy(paras, {**CARE, "insurer": "HDFC ERGO"})
    c = [r for r in recs if r["type"] == "parent" and r["clause_id"].endswith("/1") and "Pre-existing" in r["text"]][0]
    assert c["section"].startswith("SECTION C") and c["clause_id"].startswith("Section C")


def test_cross_reference_line_is_not_a_clause():
    xref = "Section B-3 (Preventive Health Check Up), Sections B-2.9 (Global Health Cover), Section B-2.11 (Travel) shall not apply"
    assert clause_id(xref, "HDFC ERGO") is None
    assert clause_id("SECTION C. WAITING PERIOD AND EXCLUSIONS", "HDFC ERGO") == "Section C"


def test_runon_caps_fixed():
    from src.rag.chunker import fix_runon_caps
    assert fix_runon_caps("STANDARDDEFINITIONS") == "STANDARD DEFINITIONS"
    assert fix_runon_caps("I - DEFINITIONS") == "I - DEFINITIONS"


def test_toc_like_paragraph_dropped():
    toc = "Section C Waiting Period & Exclusions 17 Standard Waiting Period 17 Standard Exclusions 19 Non-Medical Exclusions 21 Section D Terms"
    assert skip_toc_pages([{"page": 5, "text": toc}]) == []


def test_bare_list_number_is_qualified_by_section():
    paras = P("SECTION D. TERMS AND CONDITIONS",
              "20. Dental treatment and surgery of any kind, unless requiring hospitalisation as an in-patient")
    recs = chunk_policy(paras, {**CARE, "insurer": "HDFC ERGO"})
    ids = [r["clause_id"] for r in recs if r["type"] == "parent"]
    assert "Section D/20" in ids


def test_star_roman_heading_sets_section():
    paras = P("I - DEFINITIONS",
              "Room Rent: Room Rent means the amount charged by a Hospital towards room and boarding expenses")
    recs = chunk_policy(paras, STAR)
    r = [x for x in recs if x["type"] == "parent" and x["clause_id"] == "Def:Room Rent"][0]
    assert r["section"] == "I - DEFINITIONS"


def test_toc_page_skipped():
    paras = [{"page": 1, "text": "Table of Contents Sr. No. Particulars Page No. Preamble waiting periods"},
             {"page": 1, "text": "Waiting Periods 30"},
             {"page": 2, "text": "1. Preamble This Policy is a contract of insurance issued by the company"}]
    assert [p["page"] for p in skip_toc_pages(paras)] == [2]


def test_oversized_parent_is_split():
    para = "x" * 1200
    groups = split_parent([para] * 7)
    assert len(groups) >= 3 and all(sum(map(len, g)) <= 3600 for g in groups)
    recs = chunk_policy(P("2.5. Big clause " + "y" * 100, *[para] * 7), CARE)
    parents = [r for r in recs if r["type"] == "parent"]
    assert len(parents) >= 3 and all(r["clause_id"] == "2.5" for r in parents)
    assert len({r["chunk_id"] for r in parents}) == len(parents)


def test_old_hdfc_mixed_case_section_and_roman_items():
    long = "Section C. Waiting Period & Exclusions Standard Waiting Period All Illnesses and treatments shall be covered subject to waiting"
    assert clause_id(long, "HDFC ERGO") == "Section C"
    assert clause_id("XI. Portability The Insured Person will have the option to port the Policy", "HDFC ERGO") == "XI"
    paras = P("Section C. Waiting Period & Exclusions Standard Waiting Period All Illnesses and treatments are covered subject to terms",
              "XI. Portability The Insured Person will have the option to port the Policy to other insurers by applying")
    recs = chunk_policy(paras, {**CARE, "insurer": "HDFC ERGO"})
    ids = [r["clause_id"] for r in recs if r["type"] == "parent"]
    assert "Section C/XI" in ids
    assert all(r["section"] == "Section C" for r in recs if r["type"] == "parent")


def test_caps_item_list_with_digits_is_not_a_heading():
    assert not is_heading("X-RAY FILM 17 BOYLES APPARATUS CHARGES 18 BABY FOOD")
    from src.rag.chunker import heading_kind
    assert heading_kind("X-RAY FILM 17 BOYLES APPARATUS CHARGES", None, None) is None


def test_merged_heading_label_is_trimmed():
    from src.rag.chunker import heading_label
    assert heading_label("II - COVERAGE In consideration of the premium paid", None) == "II - COVERAGE"
    assert heading_label("SECTION C. SPECIAL TERMS AND CONDITIONS Standard Waiting Periods All", "Section C") == \
        "SECTION C. SPECIAL TERMS AND CONDITIONS"


def test_long_numbered_heading_merged_with_text_still_detected():
    from src.rag.chunker import heading_kind
    merged = "3. Coverage Under this Policy We will cover the following benefits subject to terms and conditions of this contract"
    assert heading_kind(merged, "3", "3.1") == "major"