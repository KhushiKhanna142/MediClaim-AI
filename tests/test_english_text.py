from src.ingestion.english_text import clean_span


def test_pure_english_kept():
    assert clean_span("Master Circular on Health Insurance Business") == "Master Circular on Health Insurance Business"


def test_devanagari_dropped():
    assert clean_span("स्वास्थ्य बीमा व्यवसाय संबंधी मास्टर पररपत्र") == ""


def test_garbled_hindi_dropped():
    assert clean_span("पृʿ") == ""
    assert clean_span("संदभर्") == ""
    assert clean_span("पįरपत्र") == ""


def test_pure_garbled_no_devanagari_dropped():
    assert clean_span("ːमार") == ""
    assert clean_span("ʿːį ʿ") == ""


def test_stray_junk_char_removed_from_english():
    assert clean_span("The insurer shall settle claims within thirty days ʿ of receipt") == \
        "The insurer shall settle claims within thirty days  of receipt"


def test_punctuation_and_rupee_kept():
    s = "Sum insured ₹5,00,000 – subject to 10% co-pay (clause 4.2)"
    assert clean_span(s) == s


from src.ingestion.english_text import is_residue


def test_residue_lines_from_user_output_removed():
    for line in ["III4", "22, 20242, 1946", ": 5 , 2024", "2025", ": /&///117/9/2024",
                 "xxxGIDHxxx", "1", "/ P a g e", "206]"]:
        assert is_residue(line), line


def test_real_english_lines_kept():
    for line in ["Master Circular on Health Insurance Business", "Ref: IRDAI/PP&GR/CIR/MISC/117/9/2024",
                 "PUBLISHED BY AUTHORITY", "NEW DELHI", "Date: 5th September, 2024",
                 "No. 206] NEW DELHI, MONDAY"]:
        assert not is_residue(line), line


def test_clause_markers_protected():
    for line in ["1.", "2.1.3.", "(a)", "(iv)", "12)"]:
        assert not is_residue(line), line