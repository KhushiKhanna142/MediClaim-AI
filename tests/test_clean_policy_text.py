from src.ingestion.clean_policy_text import clean_document, despace_letters, lines_to_paragraphs


def test_despace_letters():
    assert despace_letters("Central G o v e r n m e n t") == "Central Government"
    assert despace_letters("a b c") == "a b c"          # too short to touch


def test_niva_marker_on_own_line():
    lines = ["2.1.7.", "Congenital Anomaly means a condition", "present since birth.",
             "2.1.8.", "Co-payment means a cost sharing requirement"]
    paras = lines_to_paragraphs(lines)
    assert paras == ["2.1.7. Congenital Anomaly means a condition present since birth.",
                     "2.1.8. Co-payment means a cost sharing requirement"]


def test_star_one_word_per_line():
    lines = ["Maintaining", "daily", "records", "of", "the", "patients and making them accessible",
             "AYUSH Treatment: refers to treatments"]
    paras = lines_to_paragraphs(lines)
    assert paras[0] == "Maintaining daily records of the patients and making them accessible AYUSH Treatment: refers to treatments"


def test_lettered_items_stay_separate():
    paras = lines_to_paragraphs(["(a) Central or State Government AYUSH Hospital or", "(b) Teaching hospital attached"])
    assert len(paras) == 2


def test_repeated_header_removed_and_cross_page_join():
    hdr = "Care Supreme - CHIHLIP27061V032627 Know Your Policy"
    pages = []
    for n in range(1, 9):
        body = f"2.{n}. Clause number {n} text here." if n != 3 else "2.3. Clause three starts here and"
        if n == 4:
            body = "continues onto the next page."
        pages.append({"page": n, "text": f"{hdr}\n{n} / 8\n{body}"})
    res = clean_document(pages)
    texts = [p["text"] for p in res["paragraphs"]]
    assert all("Know Your Policy" not in t for t in texts)
    assert "2.3. Clause three starts here and continues onto the next page." in texts
    assert any("CHIHLIP27061V032627" in b for b in res["boilerplate"])   # kept for metadata


def test_short_doc_not_stripped():
    pages = [{"page": i, "text": "Same long repeated line here\nunique %d line" % i} for i in range(1, 4)]
    res = clean_document(pages)
    assert sum("Same long repeated line here" in p["text"] for p in res["paragraphs"]) >= 1


def test_mixed_case_section_heading_starts_new_paragraph():
    paras = lines_to_paragraphs(["20. Dental treatment of any kind, unless requiring", "Hospitalisation.",
                                 "Section D. Terms & Clauses", "Standard Terms and Conditions"])
    assert len(paras) == 2 and paras[1].startswith("Section D.")


def test_roman_heading_starts_new_paragraph():
    paras = lines_to_paragraphs(["Room Rent means the amount charged by a hospital.", "II - BENEFITS COVERED", "1. Hospitalisation"])
    assert len(paras) == 3 and paras[1] == "II - BENEFITS COVERED"


def test_xray_is_not_a_roman_heading():
    paras = lines_to_paragraphs(["Charges for the", "X-RAY film are not payable"])
    assert len(paras) == 1