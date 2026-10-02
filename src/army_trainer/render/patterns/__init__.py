"""Pattern renderers: one function per slide-spec pattern, drawing native shapes."""

from __future__ import annotations

from . import diagrams as d
from . import simple as s

# pattern name -> (layout name in templates/base.pptx, renderer)
REGISTRY = {
    "title": ("Title Slide", s.title),
    "at_a_glance": ("Content", s.at_a_glance),
    "takeaways": ("Content", s.takeaways),
    "whats_new": ("Content", s.whats_new),
    "divider": ("Section Header", s.divider),
    "key_idea": ("Content", s.key_idea),
    "process_flow": ("Content", d.process_flow),
    "cycle": ("Content", d.cycle),
    "roles": ("Content", d.roles),
    "timeline": ("Content", d.timeline),
    "checklist": ("Content", s.checklist),
    "do_dont": ("Content", d.do_dont),
    "table": ("Content", d.table),
    "big_numbers": ("Content", s.big_numbers),
    "comparison": ("Content", s.comparison),
    "decision_tree": ("Content", d.decision_tree),
    "key_terms": ("Content", d.key_terms),
    "acronyms": ("Content", d.acronyms),
    "closing": ("Content", s.closing),
}
