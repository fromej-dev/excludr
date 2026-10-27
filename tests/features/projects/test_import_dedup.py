"""Per-project article identity and duplicate detection on import."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.features.projects.dedup import normalize_title
from app.features.projects.flows import parse_pubmed_file_flow, parse_ris_file_flow
from app.features.research.models import Article


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _use_test_session(session, monkeypatch):
    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: _Ctx(session)
    )


def _ris(tmp_path, entries, name="x.ris"):
    """Write a RIS file; each entry is a dict with title/year/doi."""
    lines = []
    for e in entries:
        lines.append("TY  - JOUR")
        lines.append(f"TI  - {e['title']}")
        if e.get("year"):
            lines.append(f"PY  - {e['year']}")
        if e.get("doi"):
            lines.append(f"DO  - {e['doi']}")
        lines.append("ER  - ")
        lines.append("")
    path = tmp_path / f"abc_{name}"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _pubmed(tmp_path, pmid, doi, title="Pubmed paper", year=2020):
    text = (
        f"PMID- {pmid}\nTI  - {title}\nDP  - {year}\nAID - {doi} [doi]\n"
        "AB  - Abstract.\n\n"
    )
    path = tmp_path / "abc_p.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_normalize_title():
    assert normalize_title("  The  Cat's  Hat: A Study! ") == "the cats hat a study"
    assert normalize_title("The Cat's Hat - a study") == normalize_title(
        "the cat's hat: a STUDY."
    )
    assert normalize_title(None) == ""


def test_same_doi_in_two_projects_ris(tmp_path, a_project, session):
    p1, p2 = a_project(), a_project()
    entry = [{"title": "Paper one", "year": 2020, "doi": "10.1/abc"}]
    r1 = parse_ris_file_flow(_ris(tmp_path, entry), p1.id)
    r2 = parse_ris_file_flow(_ris(tmp_path, entry), p2.id)
    assert r1["articles_created"] == 1
    assert r2["articles_created"] == 1
    assert r2["duplicates"] == 0
    arts = session.exec(select(Article).where(Article.doi == "10.1/abc")).all()
    assert {a.project_id for a in arts} == {p1.id, p2.id}


def test_duplicate_doi_same_project_ris(tmp_path, a_project, session):
    p = a_project()
    entry = [{"title": "Paper one", "year": 2020, "doi": "10.1/abc"}]
    parse_ris_file_flow(_ris(tmp_path, entry), p.id)
    r = parse_ris_file_flow(_ris(tmp_path, entry), p.id)
    assert r["articles_created"] == 0
    assert r["duplicates"] == 1
    assert (
        len(session.exec(select(Article).where(Article.project_id == p.id)).all()) == 1
    )


def test_duplicates_within_one_file(tmp_path, a_project):
    p = a_project()
    entries = [
        {"title": "Same Thing", "year": 2021, "doi": "10.1/z"},
        {"title": "Same Thing", "year": 2021, "doi": "10.1/z"},
    ]
    r = parse_ris_file_flow(_ris(tmp_path, entries), p.id)
    assert r["articles_created"] == 1
    assert r["duplicates"] == 1


def test_title_year_duplicate_without_doi(tmp_path, a_project, session):
    p = a_project()
    parse_ris_file_flow(
        _ris(tmp_path, [{"title": "A Study of Cats: Part 1", "year": 2019}]), p.id
    )
    r = parse_ris_file_flow(
        _ris(tmp_path, [{"title": "a study of  cats - part 1.", "year": 2019}]), p.id
    )
    assert r["articles_created"] == 0
    assert r["duplicates"] == 1
    assert (
        len(session.exec(select(Article).where(Article.project_id == p.id)).all()) == 1
    )


def test_title_year_different_year_not_duplicate(tmp_path, a_project):
    p = a_project()
    parse_ris_file_flow(_ris(tmp_path, [{"title": "Cats", "year": 2019}]), p.id)
    r = parse_ris_file_flow(_ris(tmp_path, [{"title": "Cats", "year": 2020}]), p.id)
    assert r["articles_created"] == 1
    assert r["duplicates"] == 0


def test_title_year_duplicate_is_per_project(tmp_path, a_project):
    p1, p2 = a_project(), a_project()
    e = [{"title": "Cats", "year": 2019}]
    parse_ris_file_flow(_ris(tmp_path, e), p1.id)
    r = parse_ris_file_flow(_ris(tmp_path, e), p2.id)
    assert r["articles_created"] == 1


def test_same_pmid_in_two_projects_pubmed(tmp_path, a_project, session):
    p1, p2 = a_project(), a_project()
    r1 = parse_pubmed_file_flow(_pubmed(tmp_path, "111", "10.9/x"), p1.id)
    r2 = parse_pubmed_file_flow(_pubmed(tmp_path, "111", "10.9/x"), p2.id)
    assert r1["articles_created"] == 1
    assert r2["articles_created"] == 1
    assert r2["duplicates"] == 0
    assert len(session.exec(select(Article).where(Article.pmid == "111")).all()) == 2


def test_duplicate_pmid_same_project_pubmed(tmp_path, a_project):
    p = a_project()
    parse_pubmed_file_flow(_pubmed(tmp_path, "222", "10.9/y"), p.id)
    r = parse_pubmed_file_flow(_pubmed(tmp_path, "222", "10.9/y"), p.id)
    assert r["articles_created"] == 0
    assert r["duplicates"] == 1


def test_db_enforces_unique_per_project(session, a_project):
    p1, p2 = a_project(), a_project()
    session.add(Article(project_id=p1.id, title="a", doi="d", pmid="1", pmcid="c"))
    session.add(Article(project_id=p2.id, title="a", doi="d", pmid="1", pmcid="c"))
    session.commit()
    session.add(Article(project_id=p1.id, title="b", doi="d"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
