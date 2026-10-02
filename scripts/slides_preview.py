"""Render a slide spec as Claude Slides artifact files (WP 2.4 preview only, D9 palette).

usage: uv run python scripts/slides_preview.py <out-dir>  (reads specs/FM-3-09.spec.json)
The real renderer is Phase 3 (python-pptx). This only feeds the optional Claude Slides preview.
"""

import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from army_trainer.plan.nodes import NodeIndex
from army_trainer.plan.spec import DISCLAIMER
from army_trainer.structure.models import DocTree

ROOT = Path(sys.argv[1])
(ROOT / "project/slides").mkdir(parents=True, exist_ok=True)
spec = json.load(open("specs/FM-3-09.spec.json"))
idx = NodeIndex(DocTree.model_validate_json(open("data/json/FM-3-09.json").read()))
BLACK, GOLD, GOLDD, OLIVE, MID, LIGHT, PALE, WHITE, GREEN, RED = (
    "#222021",
    "#FFCD01",
    "#8A6D00",
    "#58574E",
    "#6B6B6B",
    "#E6E6E6",
    "#F2F2F2",
    "#FFFFFF",
    "#2E6B30",
    "#B3261E",
)
F = "font-family:Arial, sans-serif"
e = lambda s: html.escape(s or "", quote=True)


def cites_of(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("cite", "extra_sources") and isinstance(v, list):
                out += [c for c in v if c not in out]
            elif k == "source_table" and v and v not in out:
                out.append(v)
            else:
                cites_of(v, out)
    elif isinstance(o, list):
        for v in o:
            cites_of(v, out)
    return out


def notes(s):
    lines = [f"- {e(t['text'])}" for t in s.get("notes", {}).get("talking_points", [])]
    lines.append("Source text:")
    for c in cites_of(s, []):
        if c in idx:
            lines.append(f"[{idx.get(c).cite}] {e(idx.text(c))}")
    txt = "\n".join(lines)
    return f"<aside>{txt[:3990]}</aside>"


def footer(s):
    cs = [
        idx.get(c).cite
        for c in cites_of({k: v for k, v in s.items() if k != "notes"}, [])
        if c in idx
    ]
    cs = list(dict.fromkeys(cs))
    src = "FM 3-09, " + ", ".join(cs) if cs else "FM 3-09"
    if len(src) > 95:
        src = src[:92] + "…"
    return (
        f'<p style="position:absolute;left:96px;bottom:40px;width:1728px;font-size:24px;color:{MID}">'
        f"{e(src)} · {s['id'][1:]} · Unofficial training aid</p>"
    )


def frame(s, body, layout="display:flex;flex-direction:column;gap:32px"):
    return (
        f'<section id="{s["id"]}" data-transition="fade" style="background:{WHITE};color:{BLACK};{F};'
        f'padding:240px 96px 110px;{layout}">'
        f'<div style="position:absolute;left:0;top:0;width:1920px;height:170px;background:{BLACK}"></div>'
        f'<div style="position:absolute;left:0;top:170px;width:1920px;height:10px;background:{GOLD}"></div>'
        f'<h2 style="position:absolute;left:96px;top:44px;width:1728px;font-size:60px;font-weight:700;color:{WHITE};'
        f'text-transform:uppercase;letter-spacing:1px;line-height:1.1">{e(s["title"])}</h2>'
        f"{body}{footer(s)}{notes(s)}</section>"
    )


def card(inner, bg=PALE, extra=""):
    return f'<div style="background:{bg};border-left:8px solid {GOLD};padding:28px 32px;display:flex;flex-direction:column;gap:12px;{extra}">{inner}</div>'


P = lambda t, size=32, color=BLACK, w=400: (
    f'<p style="font-size:{size}px;color:{color};font-weight:{w};line-height:1.3">{e(t)}</p>'
)
H = lambda t, size=36, color=BLACK: (
    f'<h3 style="font-size:{size}px;font-weight:700;color:{color};line-height:1.2">{e(t)}</h3>'
)
row = lambda inner, gap=32, extra="": (
    f'<div style="display:flex;flex-direction:row;gap:{gap}px;{extra}">{inner}</div>'
)


def tiles(stats):
    return row(
        "".join(
            f'<div style="flex:1;background:{GOLD};padding:32px;display:flex;flex-direction:column;gap:8px">'
            f'<p style="font-size:96px;font-weight:700;color:{BLACK};line-height:1">{e(t["value"])}</p>{P(t["label"], 30)}</div>'
            for t in stats
        )
    )


def render(s):
    p = s["pattern"]
    if p in ("title", "closing"):
        if p == "title":
            mid = (
                f'<h1 style="font-size:96px;font-weight:700;color:{WHITE};text-transform:uppercase;line-height:1.05">{e(s["title"])}</h1>'
                + P(s.get("subtitle", ""), 40, LIGHT)
            )
        else:
            mid = (
                f'<h1 style="font-size:80px;font-weight:700;color:{WHITE};text-transform:uppercase">{e(s["title"])}</h1>'
                + "".join(P("▸ " + i["text"], 34, WHITE) for i in s["items"])
            )
        return (
            f'<section id="{s["id"]}" data-transition="fade" style="background:{BLACK};color:{WHITE};{F};padding:160px 128px;'
            f'display:flex;flex-direction:column;justify-content:center;gap:36px">'
            f'<div style="position:absolute;left:128px;top:120px;width:240px;height:12px;background:{GOLD}"></div>{mid}'
            f'<p style="position:absolute;left:128px;bottom:72px;width:1664px;font-size:26px;color:{BLACK};background:{GOLD};padding:16px 24px">{e(DISCLAIMER)}</p>'
            f"{notes(s)}</section>"
        )
    if p == "divider":
        return (
            f'<section id="{s["id"]}" data-transition="fade" style="background:{OLIVE};color:{WHITE};{F};padding:160px 128px;'
            f'display:flex;flex-direction:column;justify-content:center;gap:32px">'
            f'<p style="font-size:200px;font-weight:700;color:{GOLD};line-height:1">{e(s.get("number") or "")}</p>'
            f'<h1 style="font-size:80px;font-weight:700;color:{WHITE};text-transform:uppercase;line-height:1.1">{e(s["title"])}</h1>'
            + (P(s["blurb"]["text"], 36, WHITE) if s.get("blurb") else "")
            + f'<p style="position:absolute;left:128px;bottom:40px;width:1664px;font-size:24px;color:{LIGHT}">FM 3-09, {e(idx.get(s["chapter"]).cite)} · Unofficial training aid</p>'
            f"{notes(s)}</section>"
        )
    if p == "at_a_glance":
        body = (
            card(H("Purpose", 30, GOLDD) + P(s["purpose"]["text"], 36))
            + card(H("Applies to", 30, GOLDD) + P(s["applies_to"]["text"], 36))
            + tiles(s["stats"])
        )
        return frame(s, body)
    if p in ("takeaways", "whats_new"):
        body = "".join(
            row(
                f'<p style="font-size:40px;font-weight:700;color:{BLACK};background:{GOLD};padding:8px 20px;min-width:max-content">{n}</p>'
                + P(i["text"], 32),
                24,
                "align-items:center",
            )
            for n, i in enumerate(s["items"], 1)
        )
        return frame(s, body, "display:flex;flex-direction:column;gap:24px")
    if p == "key_idea":
        body = (
            f'<p style="font-size:48px;font-weight:700;line-height:1.25;border-left:12px solid {GOLD};padding:8px 0 8px 32px">{e(s["statement"]["text"])}</p>'
            + row("".join(card(P(i["text"], 30), extra="flex:1") for i in s["points"]))
        )
        return frame(s, body, "display:flex;flex-direction:column;gap:48px")
    if p in ("process_flow", "cycle"):
        steps = s["steps"]
        n = len(steps)
        size = 30 if n <= 4 else 26
        parts = []
        for k, st in enumerate(steps):
            parts.append(
                f'<div style="flex:1;background:{PALE};border-top:12px solid {GOLD};padding:24px;display:flex;flex-direction:column;gap:12px">'
                f'<p style="font-size:28px;font-weight:700;color:{GOLDD}">{k + 1}</p>{H(st["label"], 32)}'
                + (P(st["detail"], size) if st.get("detail") else "")
                + "</div>"
            )
            if k < n - 1:
                parts.append(
                    f'<x-shape kind="arrow-right" style="background:{BLACK};width:48px;height:28px;align-self:center"></x-shape>'
                )
        body = row("".join(parts), 12, "align-items:stretch")
        if p == "cycle":
            body += (
                f'<p style="font-size:30px;font-weight:700;color:{BLACK};background:{GOLD};padding:12px 24px;align-self:center">'
                f"↻ {e(s.get('center_label') or 'Repeats continuously')}</p>"
            )
        return frame(s, body)
    if p == "roles":
        cols = min(len(s["roles"]), 4)
        cards = "".join(
            f'<div style="background:{PALE};border-top:12px solid {BLACK};padding:24px;display:flex;flex-direction:column;gap:12px">'
            + H(r["name"] + (f" ({r['abbreviation']})" if r.get("abbreviation") else ""), 30)
            + "".join(P("• " + d["text"], 24) for d in r["duties"])
            + "</div>"
            for r in s["roles"]
        )
        return frame(
            s,
            f'<div style="display:grid;grid-template-columns:repeat({cols}, 1fr);gap:24px">{cards}</div>',
        )
    if p == "checklist":
        body = "".join(
            row(
                f'<x-icon name="CheckCircle" style="color:{GREEN};width:48px;height:48px"></x-icon>'
                + P(i["text"], 30),
                24,
                "align-items:center",
            )
            for i in s["items"]
        )
        return frame(s, body, "display:flex;flex-direction:column;gap:22px")
    if p == "do_dont":
        col = lambda head, color, items: (
            f'<div style="flex:1;display:flex;flex-direction:column;gap:20px">'
            f'<p style="font-size:40px;font-weight:700;color:{WHITE};background:{color};padding:12px 24px">{head}</p>'
            + "".join(card(P(i["text"], 30), extra=f"border-left:8px solid {color}") for i in items)
            + "</div>"
        )
        return frame(s, row(col("DO", GREEN, s["do"]) + col("DON'T", RED, s["dont"]), 48))
    if p == "table":
        ncol = len(s["columns"])
        w = round(100 / ncol)
        fs = 24 if sum(len(c) for r in s["rows"] for c in r["cells"]) > 500 else 28
        head = "".join(f'<th style="width:{w}%">{e(c)}</th>' for c in s["columns"])
        rows = "".join(
            f'<tr style="background:{PALE if k % 2 else WHITE}">'
            + "".join(f"<td>{e(c)}</td>" for c in r["cells"])
            + "</tr>"
            for k, r in enumerate(s["rows"])
        )
        return frame(
            s,
            f'<table style="font-size:{fs}px;color:{BLACK};border:1px solid {LIGHT};width:1728px">'
            f'<tr style="background:{LIGHT}">{head}</tr>{rows}</table>',
        )
    if p == "big_numbers":
        return frame(
            s,
            tiles(s["stats"]),
            "display:flex;flex-direction:column;justify-content:center;gap:32px",
        )
    if p == "comparison":
        cols = "".join(
            f'<div style="flex:1;display:flex;flex-direction:column;gap:20px">'
            f'<p style="font-size:34px;font-weight:700;color:{WHITE};background:{BLACK};padding:14px 24px">{e(c["heading"])}</p>'
            + "".join(card(P(i["text"], 28)) for i in c["points"])
            + "</div>"
            for c in s["columns"]
        )
        return frame(s, row(cols, 32))
    if p == "decision_tree":
        nodes = {x["key"]: x for x in s["nodes"]}

        def box(k, color):
            x = nodes[k]
            bg = GOLD if x["kind"] == "question" else color
            return f'<div style="flex:1;background:{bg};padding:20px 24px">{P(x["text"], 26, BLACK if bg in (GOLD, PALE) else WHITE, 700 if x["kind"] == "question" else 400)}</div>'

        rows_, k = [], s["root"]
        while k and nodes[k]["kind"] == "question":
            q = nodes[k]
            yes = (
                box(q["yes"], PALE) if nodes[q["yes"]]["kind"] == "outcome" else box(q["yes"], PALE)
            )
            rows_.append(
                row(
                    box(k, GOLD)
                    + f'<p style="font-size:28px;font-weight:700;color:{GREEN};align-self:center">YES →</p>'
                    + yes,
                    20,
                    "align-items:center",
                )
            )
            k = q["no"]
            if nodes[k]["kind"] == "outcome":
                rows_.append(
                    row(
                        f'<p style="font-size:28px;font-weight:700;color:{RED};align-self:center">NO →</p>'
                        + box(k, RED),
                        20,
                        "align-items:center",
                    )
                )
                break
            rows_.append(f'<p style="font-size:28px;font-weight:700;color:{RED}">NO ↓</p>')
        return frame(s, "".join(rows_), "display:flex;flex-direction:column;gap:20px")
    if p == "key_terms":
        cards = "".join(card(H(t["term"], 32) + P(t["definition"], 26)) for t in s["terms"])
        return frame(
            s,
            f'<div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:24px">{cards}</div>',
        )
    if p == "acronyms":
        ents = s["entries"]
        half = (len(ents) + 1) // 2
        tab = lambda es: (
            f'<table style="font-size:28px;color:{BLACK};width:840px">'
            + "".join(
                f'<tr style="background:{PALE if k % 2 else WHITE}"><td style="width:25%">{e(x["abbreviation"])}</td><td style="width:75%">{e(x["meaning"])}</td></tr>'
                for k, x in enumerate(es)
            )
            + "</table>"
        )
        return frame(s, row(tab(ents[:half]) + tab(ents[half:]), 48))
    raise SystemExit(f"no renderer for {p}")


order = []
for s in spec["slides"]:
    (ROOT / f"project/slides/{s['id']}.html").write_text(render(s), encoding="utf-8")
    order.append(s["id"])
sections = {
    "front": {"description": "Title, at a glance, takeaways and what changed.", "start": "s01"}
}
for s in spec["slides"]:
    if s["pattern"] == "divider":
        sections[s["chapter"]] = {
            "description": f"Chapter {s['number']}: {s['title']}.",
            "start": s["id"],
        }
    if s["pattern"] == "key_terms":
        sections["back"] = {
            "description": "Key terms, acronyms and where to read more.",
            "start": s["id"],
        }
deck = {
    "v": 4,
    "createdOnFiles": {"v": 1, "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
    "lists": "css",
    "title": "FM 3-09 Deck Preview",
    "order": order,
    "sections": sections,
    "faces": {},
    "designSystems": [],
}
(ROOT / "project/deck.json").write_text(json.dumps(deck, indent=1), encoding="utf-8")
print(len(order), "slides")
