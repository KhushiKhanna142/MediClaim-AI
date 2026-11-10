"""Render synthetic claims to PDFs, then degrade some to look scanned.

Usage: python -m synth.render [--claims data/synthetic_claims] [--seed 7] [--scan-frac 0.35]

For each claim folder it writes docs/<doc>.pdf for every document in claim.json's docs_present
(missing documents are deliberately not rendered) and docs/render_manifest.json recording the
layout used and whether the file was degraded to an image-only "scan". Truth for extraction
evaluation stays in claim.json. Every page carries a small "synthetic test document" footer.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BILL_LAYOUTS = ("classic", "grouped", "compact", "summary_first")
INSURER = {"niva_aspire": "Niva Bupa Health Insurance", "hdfc_optima_secure_current": "HDFC ERGO General Insurance"}
PRODUCT = {"niva_aspire": "ReAssure (Aspire)", "hdfc_optima_secure_current": "Optima Secure"}
HOSPITALS = ["Sunrise Multispeciality Hospital", "Lotus Care Hospital", "Harmony Medical Centre",
             "Metro Heart and General Hospital", "Sanjivani Hospital and Research Centre"]
CITIES = ["Pune", "Mumbai", "Nagpur", "Indore", "Jaipur", "Ahmedabad"]
CAT_TITLES = {"room": "Room and Bed Charges", "icu": "ICU Charges", "surgeon": "Professional Fees",
              "ot": "Operation Theatre", "medicine": "Pharmacy", "consumable": "Consumables",
              "investigation": "Diagnostics", "implant": "Implants", "nursing": "Nursing", "other": "Other Charges"}
CAT_ORDER = list(CAT_TITLES)


def rng_for(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


def inr(n: int) -> str:
    s = str(abs(int(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if n < 0 else "") + s


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=15, spaceAfter=4),
        "h": ParagraphStyle("h", parent=ss["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=3),
        "n": ParagraphStyle("n", parent=ss["Normal"], fontSize=9.5, leading=13),
        "s": ParagraphStyle("s", parent=ss["Normal"], fontSize=8, leading=10, textColor=colors.grey),
    }


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(15 * mm, 8 * mm, "Synthetic test document, generated for software evaluation. Not a real record.")
    canvas.drawRightString(195 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build(path: Path, flow):
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=14 * mm, bottomMargin=16 * mm).build(flow, onFirstPage=footer, onLaterPages=footer)


def kv_table(rows, widths=(55 * mm, 120 * mm), grid=True):
    t = Table(rows, colWidths=widths)
    style = [("FONTSIZE", (0, 0), (-1, -1), 9.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]
    if grid:
        style.append(("GRID", (0, 0), (-1, -1), 0.4, colors.grey))
    t.setStyle(TableStyle(style))
    return t


def ids_for(claim: dict) -> dict:
    r = rng_for(claim["claim_id"], "ids")
    pol = claim["policy_id"]
    return {"policy_no": f"{'NB' if pol.startswith('niva') else 'HD'}{r.randint(10**9, 10**10 - 1)}",
            "hospital": r.choice(HOSPITALS), "city": r.choice(CITIES),
            "bill_no": f"BL/{claim['admission_date'].year if isinstance(claim['admission_date'], date) else claim['admission_date'][:4]}/{r.randint(1000, 99999)}",
            "uhid": f"UH{r.randint(100000, 999999)}", "phone": f"9{r.randint(100000000, 999999999)}",
            "aadhaar_tail": f"{r.randint(1000, 9999)}", "doctor": f"Dr. {r.choice(['A. Kulkarni', 'S. Mehta', 'R. Nair', 'P. Deshmukh', 'V. Iyer'])}"}


def pdate(s: str) -> date:
    return date.fromisoformat(s)


# ---------------------------------------------------------------- documents
def claim_form(claim, ids, st):
    p, c = claim["patient"], claim["condition"]
    f = [Paragraph(f"{INSURER[claim['policy_id']]}", st["title"]),
         Paragraph("Health Insurance Claim Form (Reimbursement), Part A", st["n"]), Spacer(1, 6),
         kv_table([["Policy number", ids["policy_no"]], ["Product", PRODUCT[claim["policy_id"]]],
                   ["Policy start date", dmy(pdate(claim["schedule"]["policy_start"]))],
                   ["Sum insured (Rs.)", inr(claim["schedule"]["sum_insured"])],
                   ["Name of patient", p["name"]], ["Age / Sex", f"{p['age']} years / {p['sex']}"],
                   ["Contact number", ids["phone"]],
                   ["Hospital name", f"{ids['hospital']}, {ids['city']}"],
                   ["Date of admission", dmy(pdate(claim["admission_date"]))],
                   ["Date of discharge", dmy(pdate(claim["discharge_date"]))],
                   ["Diagnosis / ailment", c["name"]],
                   ["Nature of illness", "Accident / injury" if c["kind"] == "accident" else "Illness"],
                   ["Room category occupied", claim["room_claimed"].replace("_", " ")],
                   ["Total amount claimed (Rs.)", inr(claim["stated_total"])]]),
         Spacer(1, 10), Paragraph("Declaration", st["h"]),
         Paragraph("I declare that the information furnished in this claim form is true and correct to the best of my "
                   "knowledge. I agree to provide any further documents required by the insurer.", st["n"]),
         Spacer(1, 16), Paragraph(f"Signature of the insured: ____________________  Date: {dmy(pdate(claim['discharge_date']))}", st["n"])]
    return f


def group_items(items):
    groups = {}
    for it in items:
        groups.setdefault(it["category"], []).append(it)
    return [(k, groups[k]) for k in CAT_ORDER if k in groups]


def hospital_bill(claim, ids, st, layout):
    p = claim["patient"]
    items = claim["items"]
    head = [Paragraph(ids["hospital"], st["title"]), Paragraph(f"{ids['city']}  |  Final Inpatient Bill", st["n"]), Spacer(1, 6)]
    info = [["Bill no", ids["bill_no"], "UHID", ids["uhid"]],
            ["Patient", p["name"], "Age / Sex", f"{p['age']} / {p['sex']}"],
            ["Admitted", dmy(pdate(claim["admission_date"])), "Discharged", dmy(pdate(claim["discharge_date"]))],
            ["Consultant", ids["doctor"], "Room", claim["room_claimed"].replace("_", " ")]]
    it = Table(info, colWidths=[24 * mm, 60 * mm, 24 * mm, 60 * mm])
    it.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("BOX", (0, 0), (-1, -1), 0.5, colors.black)]))
    head += [it, Spacer(1, 8)]
    total_row = ["", "", "", "TOTAL", inr(claim["stated_total"])]
    hdr_style = [("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6e6e6")),
                 ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("ALIGN", (-3, 0), (-1, -1), "RIGHT")]

    if layout == "classic":
        rows = [["Sl", "Description", "Qty", "Rate", "Amount"]]
        for i, x in enumerate(items, 1):
            rows.append([str(i), x["description"], str(x["qty"]), inr(x["rate"]), inr(x["amount"])])
        rows.append(total_row)
        t = Table(rows, colWidths=[10 * mm, 90 * mm, 16 * mm, 29 * mm, 35 * mm], repeatRows=1)
        t.setStyle(TableStyle(hdr_style + [("GRID", (0, 0), (-1, -2), 0.4, colors.grey),
                                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]))
        return head + [t]

    if layout == "grouped":
        rows, extra = [["Particulars", "Qty", "Rate", "Amount"]], []
        for cat, xs in group_items(items):
            rows.append([CAT_TITLES[cat].upper(), "", "", ""])
            extra.append(len(rows) - 1)
            for x in xs:
                rows.append(["   " + x["description"], str(x["qty"]), inr(x["rate"]), inr(x["amount"])])
            rows.append(["   Sub-total", "", "", inr(sum(x["amount"] for x in xs))])
        rows.append(["GRAND TOTAL", "", "", inr(claim["stated_total"])])
        t = Table(rows, colWidths=[100 * mm, 18 * mm, 28 * mm, 34 * mm], repeatRows=1)
        sty = hdr_style + [("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                           ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)]
        for r in extra:
            sty += [("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"), ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#f3f3f3"))]
        t.setStyle(TableStyle(sty))
        return head + [t]

    if layout == "compact":
        rows = [["Item", "Amount (Rs.)"]]
        for x in items:
            label = x["description"] + (f"  ({x['qty']} x {inr(x['rate'])})" if x["qty"] > 1 else "")
            rows.append([label, inr(x["amount"])])
        rows.append(["Net payable", inr(claim["stated_total"])])
        t = Table(rows, colWidths=[135 * mm, 45 * mm], repeatRows=1)
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                               ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]))
        return head + [t]

    # summary_first: category summary on page 1, itemised detail afterwards
    srows = [["Head", "Amount"]] + [[CAT_TITLES[c], inr(sum(x["amount"] for x in xs))] for c, xs in group_items(items)]
    srows.append(["Total bill", inr(claim["stated_total"])])
    s = Table(srows, colWidths=[110 * mm, 50 * mm])
    s.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    drows = [["Date", "Description", "Qty", "Rate", "Amount"]]
    adm = pdate(claim["admission_date"])
    for x in items:
        drows.append([dmy(adm), x["description"], str(x["qty"]), inr(x["rate"]), inr(x["amount"])])
    d = Table(drows, colWidths=[24 * mm, 83 * mm, 14 * mm, 28 * mm, 31 * mm], repeatRows=1)
    d.setStyle(TableStyle(hdr_style + [("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey)]))
    from reportlab.platypus import PageBreak
    return head + [Paragraph("Summary of charges", st["h"]), s, PageBreak(), Paragraph("Itemised statement", st["h"]), d]


def discharge_summary(claim, ids, st):
    p, c = claim["patient"], claim["condition"]
    adm, dis = pdate(claim["admission_date"]), pdate(claim["discharge_date"])
    if c["is_ped"]:
        onset = pdate(claim["schedule"]["policy_start"]) - timedelta(days=548)
        history = f"Known case of {c['name']}, diagnosed on {dmy(onset)}, on regular treatment."
    elif c["kind"] == "accident":
        history = "No significant past history. Presented following a road traffic accident."
    else:
        history = "No significant past medical or surgical history."
    return [Paragraph(ids["hospital"], st["title"]), Paragraph("Discharge Summary", st["n"]), Spacer(1, 6),
            kv_table([["Patient", f"{p['name']}, {p['age']} years, {p['sex']}"], ["UHID", ids["uhid"]],
                      ["Date of admission", dmy(adm)], ["Date of discharge", dmy(dis)],
                      ["Length of stay", f"{claim['room_days']} day(s)"], ["Consultant", ids["doctor"]]], grid=False),
            Paragraph("Final diagnosis", st["h"]), Paragraph(c["name"], st["n"]),
            Paragraph("History", st["h"]), Paragraph(history, st["n"]),
            Paragraph("Course in hospital", st["h"]),
            Paragraph(f"The patient was admitted with complaints related to {c['name']}. Investigations were done and "
                      f"treatment was given as per protocol. The post-treatment period was uneventful and the patient "
                      f"was discharged in stable condition on {dmy(dis)}.", st["n"]),
            Paragraph("Advice on discharge", st["h"]),
            Paragraph("Review after 7 days with reports. Continue medicines as prescribed. Avoid strenuous activity.", st["n"]),
            Spacer(1, 18), Paragraph(f"{ids['doctor']}  (Treating consultant)", st["n"])]


def policy_schedule(claim, ids, st):
    sc, p = claim["schedule"], claim["patient"]
    room = f"Rs. {inr(sc['room_limit_per_day'])} per day" if sc["room_limit_per_day"] else "No limit (single private room or lower)"
    rows = [["Policy number", ids["policy_no"]], ["Insurer", INSURER[claim["policy_id"]]], ["Product", PRODUCT[claim["policy_id"]]],
            ["Insured person", f"{p['name']}, {p['age']} years, {p['sex']}"],
            ["Policy start date", dmy(pdate(sc["policy_start"]))], ["Sum insured (Rs.)", inr(sc["sum_insured"])],
            ["Waiting period, pre-existing diseases", f"{sc['ped_months']} months"],
            ["Waiting period, specified diseases/procedures", f"{sc['spec_months']} months"],
            ["Initial waiting period", "30 days (not applicable to accidents)"],
            ["Room rent limit", room], ["Eligible room category", sc["eligible_room"].replace("_", " ")],
            ["Co-payment", f"{sc['copay_pct']}%" if sc["copay_pct"] else "Nil"],
            ["Continuity credit (portability)", f"{sc['prior_coverage_months']} months" if sc["prior_coverage_months"] else "None"]]
    if sc["room_type_modification"]:
        rows.append(["Room type modification", "Opted (higher room category allowed with co-payment as per policy)"])
    return [Paragraph(INSURER[claim["policy_id"]], st["title"]), Paragraph("Policy Schedule", st["n"]), Spacer(1, 6), kv_table(rows)]


def id_proof(claim, ids, st):
    p = claim["patient"]
    return [Paragraph("Government of India (specimen ID card, synthetic)", st["title"]), Spacer(1, 10),
            kv_table([["Name", p["name"]], ["Age / Gender", f"{p['age']} / {p['sex']}"],
                      ["ID number", f"XXXX XXXX {ids['aadhaar_tail']}"], ["Mobile", ids["phone"]]])]


def lab_report(claim, ids, st):
    p = claim["patient"]
    rows = [["Test", "Result", "Reference"], ["Haemoglobin", "13.1 g/dL", "12.0 - 16.0"], ["WBC count", "7,400 /cmm", "4,000 - 11,000"],
            ["Blood sugar (random)", "104 mg/dL", "70 - 140"], ["Serum creatinine", "0.9 mg/dL", "0.6 - 1.2"]]
    t = Table(rows, colWidths=[70 * mm, 50 * mm, 50 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey)]))
    return [Paragraph(f"{ids['hospital']} Pathology", st["title"]),
            Paragraph(f"Patient: {p['name']}  |  Date: {dmy(pdate(claim['admission_date']))}", st["n"]), Spacer(1, 8), t]


def prescription(claim, ids, st):
    p = claim["patient"]
    return [Paragraph(ids["doctor"], st["title"]), Paragraph(ids["hospital"], st["n"]), Spacer(1, 8),
            Paragraph(f"Patient: {p['name']}, {p['age']}/{p['sex']}   Date: {dmy(pdate(claim['admission_date']))}", st["n"]),
            Paragraph(f"Diagnosis: {claim['condition']['name']}", st["n"]), Spacer(1, 8),
            Paragraph("Rx: Tab. Paracetamol 500 mg 1-0-1 x 3 days; Cap. Pantoprazole 40 mg 1-0-0 x 5 days", st["n"])]


# ---------------------------------------------------------------- scan degradation
def degrade_pdf(src: Path, dst: Path, rnd: random.Random, dpi: int = 130):
    import fitz
    import numpy as np
    from PIL import Image, ImageFilter

    doc = fitz.open(src)
    out = fitz.open()
    for page in doc:
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        img = img.rotate(rnd.uniform(-1.8, 1.8), resample=Image.BICUBIC, fillcolor=255)
        img = img.filter(ImageFilter.GaussianBlur(rnd.uniform(0.5, 1.1)))
        a = np.asarray(img, dtype=np.float32)
        a = (a - 128) * rnd.uniform(0.72, 0.9) + 128 + rnd.uniform(-12, 10)
        a += np.random.default_rng(rnd.randint(0, 2**31)).normal(0, rnd.uniform(5, 11), a.shape)
        yy = np.linspace(-1, 1, a.shape[0])[:, None]
        a *= 1 - rnd.uniform(0.04, 0.1) * (yy ** 2)          # uneven lighting
        img = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rnd.randint(40, 62))
        np_ = out.new_page(width=page.rect.width, height=page.rect.height)
        np_.insert_image(np_.rect, stream=buf.getvalue())
    out.save(dst)


# ---------------------------------------------------------------- driver
def render_claim(cdir: Path, seed: int, scan_frac: float) -> dict:
    claim = json.loads((cdir / "claim.json").read_text())
    ids, st = ids_for(claim), styles()
    out = cdir / "docs"
    out.mkdir(exist_ok=True)
    rnd = rng_for(seed, claim["claim_id"], "render")
    layout = rnd.choice(BILL_LAYOUTS)
    builders = {"policy_schedule": lambda: policy_schedule(claim, ids, st),
                "claim_form": lambda: claim_form(claim, ids, st),
                "hospital_bill": lambda: hospital_bill(claim, ids, st, layout),
                "discharge_summary": lambda: discharge_summary(claim, ids, st),
                "id_proof": lambda: id_proof(claim, ids, st),
                "lab_report": lambda: lab_report(claim, ids, st),
                "prescription": lambda: prescription(claim, ids, st)}
    manifest = {"claim_id": claim["claim_id"], "ids": ids, "bill_layout": layout, "docs": []}
    for doc in ["policy_schedule"] + list(claim["docs_present"]):
        if doc not in builders:
            continue
        digital = out / f"{doc}.pdf"
        build(digital, builders[doc]())
        scanned = rng_for(seed, claim["claim_id"], doc, "scan").random() < scan_frac
        if scanned:
            tmp = out / f"{doc}.tmp.pdf"
            digital.rename(tmp)
            degrade_pdf(tmp, digital, rng_for(seed, claim["claim_id"], doc, "deg"))
            tmp.unlink()
        manifest["docs"].append({"doc": doc, "file": digital.name, "scanned": scanned,
                                 "layout": layout if doc == "hospital_bill" else None})
    (out / "render_manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="data/synthetic_claims")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scan-frac", type=float, default=0.35)
    a = ap.parse_args()
    tot = scanned = 0
    layouts = {}
    for cdir in sorted(Path(a.claims).glob("C*/")):
        m = render_claim(cdir, a.seed, a.scan_frac)
        tot += len(m["docs"])
        scanned += sum(d["scanned"] for d in m["docs"])
        layouts[m["bill_layout"]] = layouts.get(m["bill_layout"], 0) + 1
    print(f"rendered {tot} documents, {scanned} degraded to look scanned; bill layouts: {layouts}")


if __name__ == "__main__":
    main()