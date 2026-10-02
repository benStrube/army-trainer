import pytest

from army_trainer.fetch.gate import check_distribution

A = "Army Regulation 600-20 24 July 2020 DISTRIBUTION RESTRICTION: Approved for public release; distribution is unlimited."


def test_distribution_a_passes():
    r = check_distribution(A)
    assert r.status == "pass" and r.distribution == "A"


def test_line_wrapped_statement_passes():
    r = check_distribution("Approved for public\nrelease; distribution\nis unlimited.")
    assert r.status == "pass"


@pytest.mark.parametrize("letter", list("BCDEF"))
def test_other_distribution_statements_rejected(letter):
    r = check_distribution(
        f"DISTRIBUTION STATEMENT {letter}: Distribution authorized to US Government agencies only"
    )
    assert r.status == "fail" and r.distribution == letter


@pytest.mark.parametrize("marker", ["CUI", "FOR OFFICIAL USE ONLY", "FOUO"])
def test_restricted_markings_rejected_even_with_dist_a_text(marker):
    r = check_distribution(f"{marker} {A}")
    assert r.status == "fail"


def test_missing_statement_rejected():
    r = check_distribution("Army Regulation 600-20 Army Command Policy")
    assert r.status == "fail" and r.distribution is None
