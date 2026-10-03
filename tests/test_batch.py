"""Batch mode and check-updates (WP 5.3), on synthetic PDFs in a temp project layout."""

import json
from pathlib import Path

import pytest
from pdfutil import make_pdf
from typer.testing import CliRunner

from army_trainer.batch import (
    Dirs,
    Entry,
    check_one,
    check_updates,
    parse_list,
    process,
    run_batch,
)
from army_trainer.cli import app
from army_trainer.fetch.fetch import FetchError

FRONT = (
    "Headquarters Department of the Army Washington, DC, {date} DISTRIBUTION RESTRICTION: "
    "Approved for public release; distribution is unlimited."
)
FRONT_B = (
    "Headquarters Department of the Army DISTRIBUTION STATEMENT B: Distribution authorized to "
    "US Government agencies only"
)
BODY = [
    "Chapter 1 Introduction",
    "1-1. Purpose. This regulation sets policy. Soldiers must report.",
]


def pdf(tmp: Path, name: str, date="24 July 2020", front=None, extra="") -> Path:
    return make_pdf(tmp / name, [front or FRONT.format(date=date), BODY[0], BODY[1] + extra])


@pytest.fixture
def dirs(tmp_path):
    return Dirs(**{k: tmp_path / "p" / k for k in Dirs.__dataclass_fields__})


# ---------------------------------------------------------------- list file


def test_parse_list_handles_comments_paths_and_urls():
    entries = parse_list(
        "# pilot\nFM 3-09\nar_600-20  inbox/a.pdf  # local\n"
        "AR-670-1 https://armypubs.army.mil/x.pdf\n\n"
    )
    assert [e.pub_id for e in entries] == ["FM-3-09", "AR-600-20", "AR-670-1"]
    assert entries[0].pdf is None and entries[0].url is None
    assert entries[1].pdf == Path("inbox/a.pdf")
    assert entries[2].url == "https://armypubs.army.mil/x.pdf"


def test_parse_list_rejects_duplicates_and_junk():
    with pytest.raises(ValueError, match="twice"):
        parse_list("AR-1-1\nar 1-1\n")
    with pytest.raises(ValueError, match="not a publication ID"):
        parse_list("!!!\n")


# ---------------------------------------------------------------- batch


def test_batch_runs_five_publications_through_convert_and_index(dirs, tmp_path):
    entries = [Entry(f"AR-{n}-1", pdf=pdf(tmp_path, f"{n}.pdf")) for n in range(1, 6)]
    report = run_batch(entries, dirs, stages=("fetch", "convert", "index"))
    assert [r.status for r in report.results] == ["ok"] * 5
    for e in entries:
        assert (dirs.json / f"{e.pub_id}.json").exists()
        assert (dirs.json / f"{e.pub_id}.indexes.json").exists()
    saved = json.loads((dirs.batch / "report.json").read_text())
    assert saved["counts"] == {"ok": 5} and len(saved["results"]) == 5
    assert "AR-3-1" in report.table() and "done" in report.table()


def test_a_rejected_publication_never_gets_past_the_gate_and_does_not_stop_the_rest(dirs, tmp_path):
    entries = [
        Entry("AR-1-1", pdf=pdf(tmp_path, "good.pdf")),
        Entry("AR-2-2", pdf=pdf(tmp_path, "bad.pdf", front=FRONT_B)),
        Entry("AR-3-3"),  # no input anywhere
        Entry("AR-4-4", pdf=pdf(tmp_path, "good2.pdf")),
    ]
    report = run_batch(entries, dirs, stages=("fetch", "convert", "index"))
    by = {r.pub_id: r for r in report.results}
    assert by["AR-1-1"].status == by["AR-4-4"].status == "ok"
    assert by["AR-2-2"].status == "rejected" and "gate rejected" in by["AR-2-2"].message
    assert by["AR-3-3"].status == "no_input" and "data/inbox" in by["AR-3-3"].message.replace(
        str(dirs.inbox), "data/inbox"
    )
    assert len(report.errors) == 2
    # the rejected PDF was not kept and nothing was converted for it
    assert not (dirs.raw / "AR-2-2.pdf").exists()
    assert not (dirs.json / "AR-2-2.json").exists() and not (dirs.md / "AR-2-2.md").exists()


def test_a_rejected_record_left_in_raw_is_still_refused_later(dirs, tmp_path):
    process(Entry("AR-2-2", pdf=pdf(tmp_path, "bad.pdf", front=FRONT_B)), dirs)
    again = process(Entry("AR-2-2"), dirs, stages=("convert", "index"))
    assert again.status == "rejected"
    assert not (dirs.json / "AR-2-2.json").exists()


def test_inbox_folder_supplies_pdfs_when_the_list_gives_no_source(dirs, tmp_path):
    dirs.inbox.mkdir(parents=True)
    pdf(dirs.inbox, "AR-5-5.pdf")
    res = process(Entry("AR-5-5"), dirs, stages=("fetch",))
    assert res.status == "ok" and res.steps["fetch"] == "done"
    assert (dirs.raw / "AR-5-5.pdf").exists()


def test_a_publication_without_a_spec_stops_with_a_packet_and_needs_planning(dirs, tmp_path):
    res = process(Entry("AR-1-1", pdf=pdf(tmp_path, "a.pdf")), dirs)
    assert res.status == "needs_planning" and not res.is_error
    assert res.steps["plan"] == "packet written"
    assert "render" not in res.steps and "qa" not in res.steps
    assert (dirs.packets / "AR-1-1" / "README.md").exists()
    assert not dirs.decks.exists() or not list(dirs.decks.glob("*.pptx"))


def test_a_spec_for_an_older_pdf_is_not_rendered(dirs, tmp_path):
    process(Entry("AR-1-1", pdf=pdf(tmp_path, "a.pdf")), dirs, stages=("fetch", "convert", "index"))
    dirs.specs.mkdir(parents=True)
    (dirs.specs / "AR-1-1.spec.json").write_text(json.dumps({"pub": {"source_sha256": "old"}}))
    res = process(Entry("AR-1-1"), dirs)
    assert res.status == "needs_planning" and "older revision" in res.message


def test_second_run_skips_what_is_up_to_date_and_force_redoes_it(dirs, tmp_path):
    e = Entry("AR-1-1", pdf=pdf(tmp_path, "a.pdf"))
    first = process(e, dirs, stages=("fetch", "convert", "index"))
    assert set(first.steps.values()) == {"done"}
    second = process(e, dirs, stages=("fetch", "convert", "index"))
    assert all(v.startswith("skipped") for v in second.steps.values())
    forced = process(e, dirs, stages=("fetch", "convert", "index"), force=True)
    assert set(forced.steps.values()) == {"done"}


def test_a_changed_pdf_is_refetched_and_reconverted(dirs, tmp_path):
    process(Entry("AR-1-1", pdf=pdf(tmp_path, "a.pdf")), dirs, stages=("fetch", "convert"))
    new = pdf(tmp_path, "b.pdf", date="1 May 2021", extra=" Leaders will check.")
    res = process(Entry("AR-1-1", pdf=new), dirs, stages=("fetch", "convert"))
    assert res.steps == {"fetch": "done", "convert": "done"}


def test_requested_stages_only(dirs, tmp_path):
    res = process(Entry("AR-1-1", pdf=pdf(tmp_path, "a.pdf")), dirs, stages=("fetch",))
    assert res.steps == {"fetch": "done"} and res.status == "ok"
    assert not dirs.json.exists()


def test_cli_batch_exit_codes_and_summary(dirs, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf(tmp_path, "good.pdf")
    (tmp_path / "list.txt").write_text("AR-1-1 good.pdf\n")
    r = CliRunner().invoke(app, ["batch", "list.txt", "--stages", "fetch,convert,index"])
    assert r.exit_code == 0, r.output
    assert "1 ok" in r.output and (tmp_path / "data/batch/report.json").exists()
    (tmp_path / "list.txt").write_text("AR-1-1 good.pdf\nAR-2-2\n")
    r = CliRunner().invoke(app, ["batch", "list.txt", "--stages", "fetch"])
    assert r.exit_code == 1 and "no input" in r.output
    r = CliRunner().invoke(app, ["batch", "list.txt", "--stages", "bogus"])
    assert r.exit_code == 2


def test_cli_build_runs_one_publication(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf(tmp_path, "good.pdf")
    r = CliRunner().invoke(app, ["build", "AR-1-1", "--pdf", "good.pdf"])
    assert r.exit_code == 0 and "needs_planning" in r.output


# ---------------------------------------------------------------- check-updates


def fetched(dirs, tmp_path, url=None, **kw):
    """Hold AR-1-1 (24 July 2020)."""
    from army_trainer.fetch.fetch import ingest

    ingest(pdf(tmp_path, "held.pdf", **kw), "AR-1-1", source_url=url, raw_dir=dirs.raw)


def serving(tmp_path, **kw):
    """A fetcher that 'downloads' a synthetic PDF."""

    def fetcher(url, dest):
        pdf(tmp_path, "served.pdf", **kw)
        dest.write_bytes((tmp_path / "served.pdf").read_bytes())

    return fetcher


URL = "https://armypubs.army.mil/x.pdf"


def test_unchanged_pdf_is_reported_unchanged(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)
    (r,) = check_updates([Entry("AR-1-1")], dirs, serving(tmp_path))
    assert r.status == "unchanged" and not r.is_error


def test_a_newer_revision_is_detected_by_hash_and_date(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)
    (r,) = check_updates([Entry("AR-1-1")], dirs, serving(tmp_path, date="1 May 2021", extra="!"))
    assert r.status == "changed" and "newer: 2020-07-24 -> 2021-05-01" in r.message
    assert (r.held_date, r.new_date) == ("2020-07-24", "2021-05-01")


def test_an_older_or_same_date_change_is_flagged_not_called_newer(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)
    (older,) = check_updates(
        [Entry("AR-1-1")], dirs, serving(tmp_path, date="1 May 2019", extra="!")
    )
    assert older.status == "changed" and "older than the one held" in older.message
    (same,) = check_updates([Entry("AR-1-1")], dirs, serving(tmp_path, extra=" edit"))
    assert same.status == "changed" and "same or unknown date" in same.message


def test_a_committed_spec_for_the_old_pdf_is_flagged_for_replanning(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)
    held = json.loads((dirs.raw / "AR-1-1.meta.json").read_text())["sha256"]
    dirs.specs.mkdir(parents=True)
    (dirs.specs / "AR-1-1.spec.json").write_text(json.dumps({"pub": {"source_sha256": held}}))
    (r,) = check_updates([Entry("AR-1-1")], dirs, serving(tmp_path, date="1 May 2021", extra="!"))
    assert r.spec_stale and "re-planning" in r.message


def test_a_candidate_that_fails_the_gate_is_rejected_never_adopted(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)
    before = (dirs.raw / "AR-1-1.pdf").read_bytes()
    (r,) = check_updates([Entry("AR-1-1")], dirs, serving(tmp_path, front=FRONT_B))
    assert r.status == "rejected" and r.is_error and "gate" in r.message
    assert (dirs.raw / "AR-1-1.pdf").read_bytes() == before  # read-only for data/raw
    assert not list(dirs.raw.glob(".*"))


def test_unreachable_source_is_reported_not_raised(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)

    def down(url, dest):
        raise FetchError("Download failed: 403")

    (r,) = check_updates([Entry("AR-1-1")], dirs, down)
    assert r.status == "unreachable" and r.is_error and "403" in r.message


def test_local_files_compare_against_the_inbox_and_no_source_is_explained(dirs, tmp_path):
    fetched(dirs, tmp_path)  # local file: no URL on record
    (r,) = check_updates([Entry("AR-1-1")], dirs)
    assert (
        r.status == "no_source" and "data/inbox".replace("data/inbox", str(dirs.inbox)) in r.message
    )
    dirs.inbox.mkdir(parents=True)
    pdf(dirs.inbox, "AR-1-1.pdf", date="1 May 2021", extra="!")
    (r,) = check_updates([Entry("AR-1-1")], dirs)
    assert r.status == "changed" and "newer" in r.message


def test_check_updates_defaults_to_everything_fetched_and_skips_the_unfetched(dirs, tmp_path):
    fetched(dirs, tmp_path, URL)
    results = check_updates(None, dirs, serving(tmp_path))
    assert [r.pub_id for r in results] == ["AR-1-1"]
    assert check_one(Entry("AR-9-9"), dirs).status == "no_source"


def test_downloads_stay_limited_to_armypubs(dirs, tmp_path):
    fetched(dirs, tmp_path, "https://example.com/x.pdf")
    (r,) = check_updates([Entry("AR-1-1")], dirs)  # real fetcher: refuses the host
    assert r.status == "unreachable" and "only armypubs.army.mil" in r.message


def test_cli_check_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["check-updates"])
    assert r.exit_code == 0 and "nothing fetched" in r.output
    pdf(tmp_path, "held.pdf")
    CliRunner().invoke(app, ["fetch", "AR-1-1", "--pdf", "held.pdf"])
    (tmp_path / "data/inbox").mkdir(parents=True)
    pdf(tmp_path / "data/inbox", "AR-1-1.pdf", date="1 May 2021", extra="!")
    r = CliRunner().invoke(app, ["check-updates"])
    assert r.exit_code == 0 and "changed" in r.output and "1 changed" in r.output
