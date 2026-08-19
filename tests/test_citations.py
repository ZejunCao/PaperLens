from __future__ import annotations

from app.schemas.document import ContentBlock, Document, PageLayout, Sentence
from app.services.citations import detect_citation_profile, strip_citations
from app.services.translate import collect_page_sentences


def _document(body: list[str], refs: list[str]) -> Document:
    blocks: list[ContentBlock] = []
    for order, text in enumerate(body + refs):
        blocks.append(
            ContentBlock(
                id=f"b{order}",
                page=1,
                order=order,
                bbox=[50, 50 + order * 12, 550, 60 + order * 12],
                source_text=text,
                sentences=[Sentence(id=f"s{order}", text=text, order=0)],
            )
        )
    page = PageLayout(page=1, width=612, height=792, blocks=blocks)
    return Document(
        paper_id="citation-test",
        parser="test",
        page_count=1,
        pages=[page],
        blocks=blocks,
    )


def test_detects_and_strips_numeric_square_style():
    doc = _document(
        [
            "Prior work [1] introduced the method.",
            "Later models [2], [3] improved it.",
            "The benchmark [4]–[6] is widely used.",
            "The resource is available [Online].",
            "The loss is shown in (2).",
        ],
        ["[1] A. Author, Paper.", "[2] B. Author, Paper.", "[3] C. Author, Paper."],
    )
    profile = detect_citation_profile(doc)
    assert profile.style == "numeric_square"
    assert strip_citations("Models [1], [2] use Eq. (3) [Online].", profile) == (
        "Models use Eq. (3) [Online]."
    )
    assert strip_citations("模型［1］、［2］使用公式（3）。", profile) == "模型使用公式（3）。"
    assert strip_citations("梯度幅值 [4] 或方向指标。", profile) == "梯度幅值或方向指标。"


def test_detects_author_date_but_preserves_ordinary_parentheses():
    doc = _document(
        [
            "This was established (Smith et al., 2020).",
            "A later study agrees (Jones and Lee, 2021).",
            "Two surveys confirm it (Brown, 2019; White, 2022).",
            "The method (introduced in 2020) remains useful.",
        ],
        ["Smith, J. 2020. A Paper.", "Jones, B. 2021. Another Paper."],
    )
    profile = detect_citation_profile(doc)
    assert profile.style == "author_date"
    assert strip_citations("Useful (Smith et al., 2020), especially in practice.", profile) == (
        "Useful, especially in practice."
    )
    assert strip_citations("The method (introduced in 2020) remains useful.", profile) == (
        "The method (introduced in 2020) remains useful."
    )
    assert strip_citations("该方法（Smith et al.，2020）表现良好。", profile) == "该方法表现良好。"


def test_numeric_parentheses_require_matching_reference_list():
    equations_only = _document(
        ["See (1) for loss.", "Use (2) for training.", "Result (3) follows."],
        ["References are listed alphabetically."],
    )
    assert detect_citation_profile(equations_only).style == "none"

    citations = _document(
        ["Prior work (1) agrees.", "Two studies (2, 3) disagree.", "A survey (4) follows."],
        ["1. A. Author, Paper.", "2. B. Author, Paper.", "3. C. Author, Paper."],
    )
    assert detect_citation_profile(citations).style == "numeric_parenthetical"


def test_numbered_method_list_is_not_mistaken_for_references():
    doc = _document(
        [
            "Prior work [1] introduced the method.",
            "Another study [2] extended it.",
            "A survey [3] compared both.",
            "1) Collect the images.",
            "2) Normalize each image.",
            "3) Train the model.",
            "The final result follows [4].",
            "The benchmark confirms it [5].",
            "We report the score [6].",
        ],
        ["[1] A. Author.", "[2] B. Author.", "[3] C. Author."],
    )
    profile = detect_citation_profile(doc)
    assert profile.style == "numeric_square"
    assert profile.matches == 6


def test_collection_removes_only_detected_citation_style():
    doc = _document(
        [
            "Prior work [1] introduced Eq. (2).",
            "Later work [2] confirmed it.",
            "A survey [3] summarizes both.",
        ],
        ["[1] A. Author.", "[2] B. Author.", "[3] C. Author."],
    )
    assert collect_page_sentences(doc, 1)[:3] == [
        ("s0", "Prior work introduced Eq. (2)."),
        ("s1", "Later work confirmed it."),
        ("s2", "A survey summarizes both."),
    ]
