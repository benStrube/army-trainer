"""Layout signals from a synthetic PDF built with Army-style heading fonts."""

import pymupdf

from army_trainer.convert.layout import document_title, scan

HB, TB, TR = "hebo", "tibo", "tiro"  # Helvetica-Bold (Arial stand-in), Times-Bold, Times-Roman


def _page(doc, lines, footer=None):
    page = doc.new_page(width=612, height=792)
    for y, text, font, size in lines:
        page.insert_text((72, y), text, fontname=font, fontsize=size)
    page.insert_text((72, 40), "Running header text", fontname=HB, fontsize=9)
    if footer:
        page.insert_text((500, 760), footer, fontname=HB, fontsize=9)
    return page


def test_heading_tiers_labels_wraps_and_page_labels():
    doc = pymupdf.open()
    _page(doc, [(100, "Fire Support Operations", HB, 20)])
    _page(
        doc,
        [
            (115, "Chapter 2", HB, 12),
            (134, "The Fire Support System", HB, 16),
            (200, "Body text that is not a heading.", TR, 10),
            (314, "SECTION II - FIELD ARTILLERY ORGANIZATIONS AT ECHELONS ABOVE", HB, 12),
            (328, "BRIGADE", HB, 12),
            (400, "FIRE SUPPORT PERSONNEL", TB, 14),
            (450, "FIRE SUPPORT COORDINATOR", TB, 12),
            (500, "Mission Analysis", TB, 11),
            (550, "A bold run-in sentence that ends with a period.", TB, 12),
        ],
        footer="2-1",
    )
    layouts = scan(doc)
    assert layouts[1].label == "2-1"
    got = [(h.tier, h.label, h.text) for h in layouts[1].headings]
    assert got == [
        ("T1", "Chapter 2", "The Fire Support System"),
        ("T2", None, "SECTION II - FIELD ARTILLERY ORGANIZATIONS AT ECHELONS ABOVE BRIGADE"),
        ("T3", None, "FIRE SUPPORT PERSONNEL"),
        ("T4", None, "FIRE SUPPORT COORDINATOR"),
        ("T5", None, "Mission Analysis"),
    ]
    assert document_title(layouts) == "Fire Support Operations"
