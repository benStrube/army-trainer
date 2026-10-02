"""Unit tests for the Markdown clean-up passes (no PDF needed)."""

from army_trainer.convert import blocks as B
from army_trainer.convert.layout import Heading, PageLayout


def kinds(blocks):
    return [b.kind for b in blocks]


# ---------------------------------------------------------------- parsing


def test_numbered_paragraph_misread_as_list_item_becomes_paragraph():
    md = "- 3-10. The FSCOORD must ensure the following:\n\n   - Formulate a plan.\n   - Brief it."
    bl = B.parse_page(md, 58)
    assert kinds(bl) == ["para", "bullet", "bullet"]
    assert bl[0].text.startswith("3-10. The FSCOORD")
    assert bl[1].text == "- Formulate a plan."  # de-indented under a paragraph, not nested


def test_nested_bullets_keep_depth_and_wrapped_lines_join():
    md = "- Top item\n  - Sub item that wraps\n    onto a second line\n- Next"
    bl = B.parse_page(md, 1)
    assert [b.text for b in bl] == [
        "- Top item",
        "  - Sub item that wraps onto a second line",
        "- Next",
    ]


def test_private_use_bullet_glyphs_become_list_items():
    bl = B.parse_page(" Assess options for assuming risk.", 1)
    assert bl[0].kind == "bullet" and bl[0].text == "- Assess options for assuming risk."


def test_captions_and_tables_are_typed():
    md = "**Table 1-2. Considerations (continued)**\n\n|**A**|**B**|\n|---|---|\n|x|y|"
    bl = B.parse_page(md, 1)
    assert kinds(bl) == ["caption", "table"]
    assert bl[0].text == "Table 1-2. Considerations (continued)"
    assert bl[1].rows == [["**A**", "**B**"], ["x", "y"]]


def test_fix_text_emphasis_spacing_and_cell_wraps():
    assert B.fix_text("_Destroy_is a task") == "_Destroy_ is a task"
    assert B.fix_text("|**See yourself and**<br>** the enemy.**Text|") == (
        "|**See yourself and the enemy.** Text|"
    )
    assert B.fix_text("|line one<br>line two|") == "|line one line two|"
    assert B.fix_text("|lead:<br>• item|") == "|lead:<br>• item|"


# ---------------------------------------------------------------- headings


def test_headings_come_from_layout_and_chapter_label_folds_in():
    md = (
        "### **Chapter 2**\n\n# **The Fire Support System**\n\nIntro text.\n\n"
        "### **SECTION I – FIRE SUPPORT SYSTEM: COMMAND AND**\n\n"
        "#### **CONTROL**\n\n2-1. Body.\n\n## **Not A Real Heading**"
    )
    layout = PageLayout(
        page=35,
        headings=[
            Heading(35, "T1", "The Fire Support System", 134, label="Chapter 2"),
            Heading(35, "T2", "SECTION I – FIRE SUPPORT SYSTEM: COMMAND AND CONTROL", 314),
        ],
    )
    bl = B.parse_page(md, 35)
    unplaced = B.resolve_headings(bl, layout)
    assert unplaced == []
    assert [(b.kind, b.text) for b in bl] == [
        ("heading", "Chapter 2: The Fire Support System"),
        ("para", "Intro text."),
        ("heading", "SECTION I – FIRE SUPPORT SYSTEM: COMMAND AND CONTROL"),
        ("para", "2-1. Body."),
        ("bold", "**Not A Real Heading**"),  # demoted: not a heading in the PDF
    ]


def test_heading_trapped_in_table_header_is_pulled_out():
    md = "|**SECTION I – A**|**CRONYMS AND ABBREVIATIONS**|\n|---|---|\n|**A2**|antiaccess|"
    layout = PageLayout(
        253, headings=[Heading(253, "T2", "SECTION I – ACRONYMS AND ABBREVIATIONS", 157)]
    )
    bl = B.parse_page(md, 253)
    B.resolve_headings(bl, layout)
    assert kinds(bl) == ["heading", "table"]
    assert bl[1].rows == [["**A2**", "antiaccess"]]


def test_zones_drop_front_lists_and_index_and_set_levels():
    def h(text, tier, page):
        return B.Block("heading", text, page, tier=tier)

    bl = [
        h("Contents", "T1", 3),
        B.Block("para", "toc line", 3),
        h("Preface", "T1", 9),
        B.Block("para", "preface text", 9),
        h("Chapter 1: Foundations", "T1", 15),
        h("FIRE SUPPORT AND THE THREAT", "T3", 15),
        h("TENETS", "T4", 17),
        h("Index", "T1", 279),
        B.Block("para", "index junk", 279),
    ]
    kept = B.assign_zones(bl)
    assert [b.text for b in kept] == [
        "Preface",
        "preface text",
        "Chapter 1: Foundations",
        "FIRE SUPPORT AND THE THREAT",
        "TENETS",
    ]
    assert [b.level for b in kept if b.kind == "heading"] == [1, 1, 2, 3]


# ---------------------------------------------------------------- tables


def test_continued_table_parts_merge_and_repeat_header_drops():
    bl = [
        B.Block("caption", "Table 1-2. Things", 19),
        B.Block("table", "", 19, rows=[["H1", "H2"], ["a", "b"]]),
        B.Block("caption", "Table 1-2. Things (continued)", 20),
        B.Block("table", "", 20, rows=[["H1", "H2"], ["c", "d"]]),
        B.Block("para", "After.", 20),
    ]
    assert B.merge_continued_tables(bl) == 1
    assert kinds(bl) == ["caption", "table", "para"]
    assert bl[1].rows == [["H1", "H2"], ["a", "b"], ["c", "d"]]


def test_repair_table_merges_split_rows_and_extracts_legend():
    t = B.Block(
        "table",
        "",
        19,
        rows=[
            ["Imperative", "Considerations"],
            ["**See yourself.** Text", "• one"],
            ["", "• two"],
            ["ACM – airspace coordinating measure, C2 – comm", "and and control"],
        ],
    )
    legend, fixes = B.repair_table(t)
    assert t.rows == [
        ["Imperative", "Considerations"],
        ["**See yourself.** Text", "• one<br>• two"],
    ]
    assert legend is not None and legend.kind == "note"
    assert legend.text == "ACM – airspace coordinating measure, C2 – command and control"
    assert fixes == 3


def test_repair_table_keeps_acronym_rows_apart():
    t = B.Block(
        "table", "", 1, rows=[["Acronym", "Meaning"], ["**ACM**", "airspace coordinating measure"]]
    )
    B.repair_table(t)
    assert t.rows[1] == ["**ACM**", "airspace coordinating measure"]


def test_table_overflow_paragraph_is_absorbed_into_cell():
    cell = "Designate, weight, and sustain the main effort. Commanders face competing demands"
    bl = [
        B.Block("table", "", 20, rows=[["H"], [cell]]),
        B.Block("para", cell + " for limited resources.", 20),
        B.Block("para", "1-19. Next paragraph.", 21),
    ]
    assert B.absorb_table_overflow(bl) == 1
    assert kinds(bl) == ["table", "para"]
    assert bl[0].rows[1][0].endswith("for limited resources.")


# ---------------------------------------------------------------- page-break joins


def test_join_paragraph_split_by_page_break():
    bl = [
        B.Block("para", "1-10. Planning is of paramount importance in any", 16),
        B.Block("para", "confrontation with a threat.", 17),
        B.Block("para", "1-11. Next.", 17),
    ]
    log = []
    assert B.join_page_breaks(bl, log) == 1
    assert (
        bl[0].text
        == "1-10. Planning is of paramount importance in any confrontation with a threat."
    )
    assert log and kinds(bl) == ["para", "para"]


def test_join_skips_a_table_at_top_of_next_page_and_keeps_hyphen():
    bl = [
        B.Block("para", "Fires must be large-", 30),
        B.Block("table", "", 31, rows=[["h"], ["r"]]),
        B.Block("para", "scale and timely.", 31),
    ]
    B.join_page_breaks(bl)
    assert bl[0].text == "Fires must be large-scale and timely."
    assert kinds(bl) == ["para", "table"]


def test_no_join_into_numbered_paragraph_heading_or_after_legend():
    bl = [
        B.Block("para", "The list continues with", 10),
        B.Block("para", "2-5. A new numbered paragraph.", 11),
        B.Block("note", "FA – field artillery, FS – fire support", 11),
        B.Block("para", "MOE1: something.", 12),
    ]
    assert B.join_page_breaks(bl) == 0


def test_no_join_on_same_page():
    bl = [
        B.Block("para", "A heading-like line without punctuation", 5),
        B.Block("para", "and more", 5),
    ]
    assert B.join_page_breaks(bl) == 0


# ---------------------------------------------------------------- glossary and output


def test_glossary_terms_and_acronyms():
    z = "Glossary"
    bl = [
        B.Block("heading", "SECTION I – ACRONYMS AND ABBREVIATIONS", 253, zone=z),
        B.Block("table", "", 253, rows=[["**A2**", "antiaccess"]], zone=z),
        B.Block("table", "", 254, rows=[["**ACM**", "airspace coordinating measure"]], zone=z),
        B.Block("heading", "SECTION II – TERMS", 256, zone=z),
        B.Block("bold", "**air interdiction**", 256, zone=z),
        B.Block("para", "Air operations to perform interdiction. (JP 3-03)", 256, zone=z),
    ]
    assert B.format_glossary(bl) == 1
    assert bl[1].rows == [
        ["Acronym", "Meaning"],
        ["**A2**", "antiaccess"],
        ["**ACM**", "airspace coordinating measure"],
    ]
    assert bl[3].text == "**air interdiction** — Air operations to perform interdiction. (JP 3-03)"


def test_render_inserts_page_markers_with_printed_labels():
    bl = [
        B.Block("heading", "Chapter 1: X", 15, level=1),
        B.Block("para", "1-1. Text.", 15),
        B.Block("table", "", 16, rows=[["a", "b|c"], ["1", "2"]]),
    ]
    out = B.render(bl, {15: "1-1", 16: "1-2"})
    assert out == (
        "<!-- page 15 (1-1) -->\n\n# Chapter 1: X\n\n1-1. Text.\n\n<!-- page 16 (1-2) -->\n\n"
        "| a | b\\|c |\n| --- | --- |\n| 1 | 2 |\n"
    )
