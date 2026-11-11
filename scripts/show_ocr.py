"""Show what OCR reads for one document at two resolutions.  python scripts/show_ocr.py C010_niva_reject_specified [policy_schedule]
Prints only the lines that matter for the schedule (waiting periods), so you can see the digit errors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf

from src.baseline.ocr import OCR_DPI, _ocr_image
import tempfile

claim = sys.argv[1]
doc = sys.argv[2] if len(sys.argv) > 2 else "policy_schedule"
pdf = Path(f"data/synthetic_claims/{claim}/docs/{doc}.pdf")
page = pymupdf.open(pdf)[0]
print("text layer characters:", len(page.get_text().strip()), "| OCR_DPI in code:", OCR_DPI)
for dpi in (200, 300):
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "p.png"
        page.get_pixmap(dpi=dpi).save(png)
        text = _ocr_image(png)
    print(f"\n--- {dpi} dpi ---")
    for line in text.splitlines():
        if "waiting" in line.lower() or "months" in line.lower() or "sum insured" in line.lower():
            print("  ", line)