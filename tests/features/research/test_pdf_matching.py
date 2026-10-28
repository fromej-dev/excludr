"""Unit tests for matching uploaded PDFs to articles (no PDFs needed)."""

from app.features.research.models import Article
from app.features.research.pdf_matching import (
    ArticleIndex,
    PdfFingerprint,
    doi_key,
    first_author_surname,
    match_pdf,
    text_key,
)

TITLE_A = "Parenting stress and child anxiety: a longitudinal cohort study"
TITLE_B = "Mindfulness-based interventions for parents of children with autism"


def _articles() -> list[Article]:
    return [
        Article(
            id=1,
            title=TITLE_A,
            authors=["Smith, John"],
            year=2020,
            doi="https://doi.org/10.1016/j.jad.2020.01.002",
            pmid="31234567",
            pmcid="PMC7000001",
        ),
        Article(
            id=2,
            title=TITLE_B,
            authors=["Jansen J"],
            year=2019,
            doi="10.1007/s10826-019-01234-5",
            pmid="30111222",
        ),
        Article(id=3, title="Editorial", authors=[], year=2021),
    ]


def _match(**fp):
    fp.setdefault("filename", "paper.pdf")
    return match_pdf(PdfFingerprint(**fp), ArticleIndex(_articles()))


def test_keys_ignore_case_punctuation_accents_and_tags():
    assert text_key("Café <i>Stress</i>-Test,\n 2020") == "cafestresstest2020"
    assert doi_key("doi:10.1016/J.JAD.2020.01.002") == doi_key(
        "https://doi.org/10.1016/j.jad.2020.01.002"
    )
    assert first_author_surname(["Smith, John"]) == "Smith"
    assert first_author_surname(["Smith J"]) == "Smith"
    assert first_author_surname([]) is None


def test_doi_in_metadata_is_a_high_match():
    outcome = _match(metadata_text="doi:10.1016/j.jad.2020.01.002")
    assert outcome.match.article_id == 1
    assert outcome.match.method == "doi_metadata"
    assert outcome.match.confidence == "high"


def test_doi_in_filename_with_slash_replaced():
    outcome = _match(filename="10.1007_s10826-019-01234-5.pdf")
    assert outcome.match.article_id == 2
    assert outcome.match.method == "doi_filename"


def test_pmid_and_pmcid_in_filename():
    assert _match(filename="PMID31234567.pdf").match.article_id == 1
    assert _match(filename="30111222.pdf").match.article_id == 2
    outcome = _match(filename="PMC7000001.pdf")
    assert (outcome.match.article_id, outcome.match.method) == (1, "pmcid_filename")


def test_article_id_filename_from_excludr_download():
    outcome = _match(filename="article-2 (1).pdf")
    assert (outcome.match.article_id, outcome.match.method) == (
        2,
        "article_id_filename",
    )
    assert _match(filename="article-99.pdf").match is None


def test_doi_split_over_lines_in_page_text_is_found_and_confirmed_by_title():
    page = f"{TITLE_A.replace(' and', chr(10) + 'and')}\nJohn Smith\nhttps://doi.org/10.1016/j.jad.\n2020.01.002"
    outcome = _match(page_text=page)
    assert outcome.match.article_id == 1
    assert outcome.match.method == "doi_text"
    assert outcome.match.confidence == "high"


def test_cited_doi_without_title_is_only_medium_and_others_low():
    # Page 1 cites both articles' DOIs but shows neither title
    page = "References 10.1007/s10826-019-01234-5 and 10.1016/j.jad.2020.01.002"
    outcome = _match(page_text=page)
    assert outcome.match.article_id == 2
    assert outcome.match.confidence == "medium"
    assert {c.article_id: c.confidence for c in outcome.candidates} == {
        2: "medium",
        1: "low",
    }


def test_title_on_first_page_with_author_is_high():
    page = f"Journal of Things\n{TITLE_B.upper()}\nA. Jansen, B. Other\nAbstract ..."
    outcome = _match(page_text=page)
    assert outcome.match.article_id == 2
    assert outcome.match.method == "title_text"
    assert outcome.match.confidence == "high"


def test_title_alone_without_author_or_year_is_medium():
    outcome = _match(page_text=f"{TITLE_B}\nNobody")
    assert outcome.match.confidence == "medium"


def test_reference_manager_filename():
    outcome = _match(filename=f"Smith - 2020 - {TITLE_A.replace(':', '_')}.pdf")
    assert outcome.match.article_id == 1
    assert outcome.match.method == "title_filename"
    assert outcome.match.confidence == "high"


def test_truncated_title_in_filename_needs_author_and_year():
    short = TITLE_A[:50]
    assert _match(filename=f"Smith - 2020 - {short}.pdf").match.article_id == 1
    weak = _match(filename=f"{short}.pdf")
    assert weak.match is None
    assert weak.candidates[0].confidence == "low"


def test_metadata_title():
    outcome = _match(metadata_title=TITLE_A + ".")
    assert outcome.match.method == "title_metadata"


def test_short_titles_are_ignored():
    assert _match(page_text="Editorial\n2021").candidates == []


def test_ties_are_not_matched_automatically():
    articles = _articles() + [
        Article(id=4, title=TITLE_A, authors=["Smith, J"], year=2020)
    ]
    outcome = match_pdf(
        PdfFingerprint(filename="x.pdf", page_text=f"{TITLE_A}\nSmith 2020"),
        ArticleIndex(articles),
    )
    assert outcome.match is None
    assert {c.article_id for c in outcome.candidates} == {1, 4}


def test_identifier_beats_title_of_another_article():
    outcome = _match(
        filename="PMID30111222.pdf", page_text=f"{TITLE_A}\nSmith 2020 (cited)"
    )
    assert outcome.match.article_id == 2
    assert [c.article_id for c in outcome.candidates] == [2, 1]


def test_conflicting_identifiers_are_not_matched():
    outcome = _match(
        filename="PMID30111222.pdf", metadata_text="10.1016/j.jad.2020.01.002"
    )
    assert outcome.match is None


def test_unmatched_pdf():
    outcome = _match(filename="scan_0001.pdf")
    assert outcome.match is None
    assert outcome.candidates == []
