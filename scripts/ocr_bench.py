"""Find the OCR settings that read the scanned policy schedules correctly on THIS machine's Tesseract. No API calls.

  python3 -m scripts.ocr_bench            # all scanned schedules
  python3 -m scripts.ocr_bench --limit 4  # quick check

For every scanned policy_schedule.pdf it runs each variant and checks that both waiting-period numbers were read
correctly against claim.json, then prints variants from best to worst.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter, ImageOps

PED = re.compile(r"pre-?existing\s+disease\w*\W{0,5}(\d+)\s*months", re.I)
SPEC = re.compile(r"procedures\W{0,5}(\d+)\s*months", re.I)


def prep(img: Image.Image, how: str) -> Image.Image:
    if how == "plain":
        return img
    if how == "sharpen":
        return img.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))
    if how == "binarize":
        a = np.asarray(ImageOps.autocontrast(img, cutoff=1), dtype=np.float32)
        return Image.fromarray(((a > a.mean() - 0.1 * a.std()) * 255).astype("uint8"))
    raise ValueError(how)


def ocr(img: Image.Image, psm: int) -> str:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "p.png"
        img.save(p)
        return subprocess.run(["tesseract", str(p), "stdout", "--psm", str(psm)], capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    docs = []
    for d in sorted(Path(a.claims).glob("C*/")):
        m = json.loads((d / "docs" / "render_manifest.json").read_text())
        if any(x["doc"] == "policy_schedule" and x["scanned"] for x in m["docs"]):
            docs.append((d, json.loads((d / "claim.json").read_text())["schedule"]))
    docs = docs[: a.limit]
    variants = [(dpi, psm, how) for dpi in (200, 300, 400) for psm in (4, 6, 11) for how in ("plain", "sharpen")]
    renders = {}
    for d, _ in docs:
        page = pymupdf.open(d / "docs" / "policy_schedule.pdf")[0]
        for dpi in (200, 300, 400):
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            renders[(d.name, dpi)] = Image.frombytes("L", (pix.width, pix.height), pix.samples)

    def run(task):
        (d, sched), (dpi, psm, how) = task
        t = ocr(prep(renders[(d.name, dpi)], how), psm)
        p, s = PED.search(t), SPEC.search(t)
        return (dpi, psm, how), bool(p and int(p.group(1)) == sched["ped_months"] and s and int(s.group(1)) == sched["spec_months"])

    tasks = [(doc, v) for doc in docs for v in variants]
    score = {v: 0 for v in variants}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for v, ok in ex.map(run, tasks):
            score[v] += ok
    print(f"scanned schedules: {len(docs)}\n{'dpi':>5} {'psm':>4} {'prep':>9}  correct")
    for (dpi, psm, how), n in sorted(score.items(), key=lambda kv: -kv[1]):
        print(f"{dpi:>5} {psm:>4} {how:>9}  {n}/{len(docs)}")


if __name__ == "__main__":
    main()