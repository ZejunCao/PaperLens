from __future__ import annotations

from app.parsers.utils import split_sentences


def test_et_al_before_year_paren_stays_one_sentence():
    text = "More recently, Kitaev et al. ( 2020 ) proposed Reformer."
    assert split_sentences(text) == [text]


def test_et_al_before_capital_stays_one_sentence():
    text = "Kitaev et al. proposed Reformer for long sequences."
    assert split_sentences(text) == [text]


def test_two_citations_still_split_on_real_boundary():
    text = (
        "Smith et al. (2020) proposed X. "
        "Jones et al. (2021) followed with Y."
    )
    parts = split_sentences(text)
    assert len(parts) == 2
    assert parts[0].endswith("proposed X.")
    assert parts[1].startswith("Jones et al.")


def test_eg_ie_and_fig_abbrev():
    assert split_sentences("Use dropout, e.g. 0.1 rate, carefully.") == [
        "Use dropout, e.g. 0.1 rate, carefully."
    ]
    assert split_sentences("See Fig. A for details. Then we continue.") == [
        "See Fig. A for details.",
        "Then we continue.",
    ]


def test_normal_sentence_boundary_unchanged():
    assert split_sentences("Hello world. Second sentence.") == [
        "Hello world.",
        "Second sentence.",
    ]


def test_eqs_then_real_boundary():
    text = "We rewrite Eqs. 4-7 below. The next section discusses training."
    parts = split_sentences(text)
    assert len(parts) == 2
    assert "Eqs. 4-7" in parts[0]
    assert parts[1].startswith("The next section")
