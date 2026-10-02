from pathlib import Path

import pytest
from pptx import Presentation

from army_trainer.plan.spec import SlideSpec
from army_trainer.render.deck import render_slides
from army_trainer.render.patterns import REGISTRY
from army_trainer.render.template import build_template

FIXTURE = Path(__file__).parent / "fixtures" / "spec_all_patterns.json"
FM = Path(__file__).parents[1] / "specs" / "FM-3-09.spec.json"


@pytest.fixture(scope="module")
def tpl(tmp_path_factory):
    return build_template(tmp_path_factory.mktemp("t") / "base.pptx")


def test_registry_covers_every_pattern():
    spec = SlideSpec.model_validate_json(FIXTURE.read_text())
    assert {s.pattern for s in spec.slides} <= set(REGISTRY)


def test_fixture_renders_every_pattern_without_overflow(tmp_path, tpl):
    spec = SlideSpec.model_validate_json(FIXTURE.read_text())
    out = tmp_path / "d.pptx"
    ctx = render_slides(spec, out, tpl)
    assert len(Presentation(out).slides) == len(spec.slides)
    assert ctx.warnings == []


def test_fm_3_09_spec_renders(tmp_path, tpl):
    """Every slide draws; fit warnings (est. overflow at the font floor) are for 3.3 to split."""
    spec = SlideSpec.model_validate_json(FM.read_text())
    out = tmp_path / "d.pptx"
    render_slides(spec, out, tpl)
    assert len(Presentation(out).slides) == len(spec.slides)


def test_text_is_copied_exactly(tmp_path, tpl):
    spec = SlideSpec.model_validate_json(FIXTURE.read_text())
    out = tmp_path / "d.pptx"
    render_slides(spec, out, tpl)
    texts = {
        t_
        for sl in Presentation(out).slides
        for sh in sl.shapes
        if sh.has_text_frame
        for t_ in [sh.text_frame.text]
    }
    for s in spec.slides:
        if s.pattern in {"takeaways", "checklist", "whats_new"}:
            for it in s.items:
                assert it.text in texts


def _render_fixture(tmp_path, tpl):
    spec = SlideSpec.model_validate_json(FIXTURE.read_text())
    out = tmp_path / "d.pptx"
    render_slides(spec, out, tpl)
    return spec, list(Presentation(out).slides)


def _runs(slide):
    return [
        (r.text, r.font.size.pt)
        for sh in slide.shapes
        if sh.has_text_frame
        for pa in sh.text_frame.paragraphs
        for r in pa.runs
        if r.font.size
    ]


def test_callout_label_is_drawn_on_the_slide_that_has_one(tmp_path, tpl):
    spec, slides = _render_fixture(tmp_path, tpl)
    flagged = [i for i, s in enumerate(spec.slides) if getattr(s, "callout", None)]
    assert flagged, "fixture needs a callout slide"
    for i, (s, sl) in enumerate(zip(spec.slides, slides, strict=True)):
        words = [t_ for t_, _ in _runs(sl) if t_ in ("CAUTION", "WARNING")]
        assert (words == [s.callout.upper()]) if i in flagged else words == []
    # the title keeps clear of the label
    chip = next(
        sh
        for sh in slides[flagged[0]].shapes
        if sh.has_text_frame and sh.text_frame.text == "CAUTION"
    )
    title = slides[flagged[0]].shapes.title
    assert title.left + title.width <= chip.left


def test_warning_callout_uses_red(tmp_path, tpl):
    from army_trainer.render.shapes import CALLOUTS, P

    assert CALLOUTS["warning"][1] == P.dont_red and CALLOUTS["caution"][1] == P.army_gold


def test_big_number_caveat_is_drawn_at_body_size_and_values_stay_on_one_line(tmp_path, tpl):
    spec, slides = _render_fixture(tmp_path, tpl)
    i = next(i for i, s in enumerate(spec.slides) if s.pattern == "big_numbers")
    s, runs = spec.slides[i], _runs(slides[i])
    assert s.caveat is not None
    assert (s.caveat.text, 20.0) in runs
    from army_trainer.render.shapes import CONTENT_W, est_lines

    n = len(s.stats)
    inner = (CONTENT_W - 0.2 * (n - 1)) / n - 0.2  # tile width less the text padding
    for st in s.stats:
        size = next(sz for t_, sz in runs if t_ == st.value)
        assert size >= 24 and est_lines(st.value, inner, size, True) == 1


def test_sibling_boxes_share_one_font_size(tmp_path, tpl):
    from army_trainer.render.shapes import Ctx, box, equalize

    prs = Presentation(tpl)
    slide = prs.slides.add_slide(prs.slide_layouts[2])
    ctx = Ctx()
    short, long_ = "Short.", "A much longer sentence that needs more room than the box has. " * 3
    a = box(slide, 1, 1, 3, 1, short, ctx=ctx, size=20)
    b = box(slide, 5, 1, 3, 1, long_, ctx=ctx, size=20)
    sizes = lambda sh: {r.font.size.pt for p in sh.text_frame.paragraphs for r in p.runs}  # noqa: E731
    assert sizes(a) != sizes(b)
    equalize(ctx)
    assert sizes(a) == sizes(b) and max(sizes(a)) < 20


def test_table_text_never_goes_below_14_pt(tmp_path, tpl):
    spec = SlideSpec.model_validate_json(FM.read_text())
    out = tmp_path / "d.pptx"
    render_slides(spec, out, tpl)
    for sl in Presentation(out).slides:
        for sh in sl.shapes:
            if getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows:
                    for cell in row.cells:
                        for pa in cell.text_frame.paragraphs:
                            for r in pa.runs:
                                assert r.font.size.pt >= 14


def _arrowheads(slide):
    return len(slide._element.xpath(".//a:ln/a:tailEnd[@type='triangle']"))


def _fixture_slide(tmp_path, tpl, pattern):
    spec, slides = _render_fixture(tmp_path, tpl)
    i = next(i for i, s in enumerate(spec.slides) if s.pattern == pattern)
    return spec.slides[i], slides[i]


def test_decision_tree_draws_an_arrow_for_every_branch_and_a_yes_no_pill(tmp_path, tpl):
    s, sl = _fixture_slide(tmp_path, tpl, "decision_tree")
    branches = sum(1 for n in s.nodes if n.kind == "question") * 2
    assert _arrowheads(sl) == branches
    texts = [sh.text_frame.text for sh in sl.shapes if sh.has_text_frame]
    assert texts.count("YES") == texts.count("NO") == branches // 2
    for n in s.nodes:  # every node's text is on the slide, unchanged
        assert n.text in texts


def test_cycle_is_a_ring_of_arrows_one_per_step(tmp_path, tpl):
    s, sl = _fixture_slide(tmp_path, tpl, "cycle")
    assert _arrowheads(sl) == len(s.steps)


def test_comparison_panels_line_up_across_columns(tmp_path, tpl):
    s, sl = _fixture_slide(tmp_path, tpl, "comparison")
    texts = {it.text for c in s.columns for it in c.points}
    panels = [sh for sh in sl.shapes if sh.has_text_frame and sh.text_frame.text in texts]
    assert len(panels) == len(texts)
    assert len({sh.height for sh in panels}) == 1  # one height
    tops = {sh.top for sh in panels}
    assert len(tops) == max(len(c.points) for c in s.columns)  # rows align across columns


def test_key_term_cards_have_a_term_tab_over_the_definition(tmp_path, tpl):
    s, sl = _fixture_slide(tmp_path, tpl, "key_terms")
    by_text = {sh.text_frame.text: sh for sh in sl.shapes if sh.has_text_frame}
    for tm in s.terms:
        tab, body = by_text[tm.term], by_text[tm.definition]
        assert tab.left == body.left and tab.width == body.width
        assert tab.top + tab.height == body.top  # the tab sits directly on the definition
        sizes = {r.font.size.pt for pa in body.text_frame.paragraphs for r in pa.runs}
        assert min(sizes) >= 16
