"""RIS imports: N2 abstracts and missing abstracts filled in from PubMed."""

import httpx
from sqlmodel import select

from app.features.research.models import Article
from app.features.research.pubmed_service import PubMedService

PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>11111111</PMID>
      <Article>
        <ArticleTitle>Exercise and Sleep: a Trial.</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Sleep matters.</AbstractText>
          <AbstractText Label="RESULTS">Exercise <i>helps</i>.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="pubmed">11111111</ArticleId></ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>22222222</PMID>
      <Article>
        <ArticleTitle>Something else entirely</ArticleTitle>
        <Abstract><AbstractText>Wrong abstract.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>33333333</PMID>
      <Article>
        <ArticleTitle>Title worded differently in PubMed</ArticleTitle>
        <Abstract><AbstractText>Matched by DOI.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList><ArticleId IdType="doi">10.1/DOI-MATCH</ArticleId></ArticleIdList>
      <ReferenceList><Reference><ArticleIdList>
        <ArticleId IdType="doi">10.9/a-reference</ArticleId>
      </ArticleIdList></Reference></ReferenceList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>"""

RIS = """TY  - JOUR
TI  - Article with an N2 abstract
N2  - Abstract from the N2 tag.
ER  -

TY  - JOUR
TI  - Exercise and sleep - a trial
AN  - 11111111
ER  -

TY  - JOUR
TI  - An Embase record
AN  - 22222222
ER  -

TY  - JOUR
TI  - Matched by its DOI
DO  - 10.1/doi-match
AN  - 33333333
ER  -

TY  - JOUR
TI  - A Web of Science record
AN  - WOS:000123456700001
ER  -

TY  - JOUR
TI  - Already has an abstract
AB  - Own abstract.
AN  - 44444444
ER  -
"""


def _use_test_session(session, monkeypatch):
    class Ctx:
        """Like ``get_prefect_session``: commits on a clean exit."""

        def __enter__(self):
            return session

        def __exit__(self, exc_type, *a):
            if exc_type is None:
                session.commit()
            return False

    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: Ctx()
    )


def _fake_pubmed(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=PUBMED_XML)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        PubMedService, "_client", lambda self: httpx.Client(transport=transport)
    )
    return requests


def _upload(client, project, content: str):
    return client.post(
        f"/api/v1/projects/{project.id}/upload/ris",
        files={"file": ("refs.ris", content.encode(), "application/x-research-info")},
    )


def _abstracts(session, project) -> dict[str, str | None]:
    session.expire_all()
    articles = session.exec(select(Article).where(Article.project_id == project.id))
    return {a.title: a.abstract for a in articles}


def test_ris_import_reads_n2_and_fills_missing_abstracts(
    auth_as, a_project, session, monkeypatch
):
    _use_test_session(session, monkeypatch)
    requests = _fake_pubmed(monkeypatch)
    client, user = auth_as()
    project = a_project(user)

    res = _upload(client, project, RIS)

    assert res.status_code == 200
    assert res.json()["result"]["abstracts_fetched"] == 2
    assert _abstracts(session, project) == {
        "Article with an N2 abstract": "Abstract from the N2 tag.",
        "Exercise and sleep - a trial": "BACKGROUND: Sleep matters. RESULTS: Exercise helps.",
        # The accession number is a PMID of another article: titles differ
        "An Embase record": None,
        "Matched by its DOI": "Matched by DOI.",
        "A Web of Science record": None,
        "Already has an abstract": "Own abstract.",
    }
    # One request, only for numeric accession numbers of articles without an abstract
    (request,) = requests
    assert request.url.params["id"] == "11111111,22222222,33333333"


def test_ris_import_survives_pubmed_being_down(
    auth_as, a_project, session, monkeypatch
):
    # The autouse fixture answers every PubMed request with a 503
    _use_test_session(session, monkeypatch)
    client, user = auth_as()
    project = a_project(user)

    res = _upload(client, project, RIS)

    assert res.status_code == 200
    assert res.json()["result"]["abstracts_fetched"] == 0
    assert _abstracts(session, project)["Exercise and sleep - a trial"] is None


def test_ris_import_without_missing_abstracts_makes_no_request(
    auth_as, a_project, session, monkeypatch
):
    _use_test_session(session, monkeypatch)
    requests = _fake_pubmed(monkeypatch)
    client, user = auth_as()
    project = a_project(user)

    with open("./tests/docs/test.ris", "rb") as f:
        res = _upload(client, project, f.read().decode())

    assert res.status_code == 200
    assert res.json()["result"]["abstracts_fetched"] == 0
    assert requests == []


IDENTIFIERS_RIS = """TY  - JOUR
TI  - Prefixed PMID with the PMCID in a note
DO  - 10.3390/ijerph17020603
AN  - PMID: 31963506
UR  - https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7014402/
N1  - PMCID: PMC7014402 (open access, CC BY 4.0)
AB  - Has an abstract.
ER  -

TY  - JOUR
TI  - PMCID only in the link
UR  - https://pmc.ncbi.nlm.nih.gov/articles/PMC8150277/
AB  - Has an abstract.
ER  -

TY  - JOUR
TI  - PMCID in C2
C2  - PMC6950277
AN  - 31835477
AB  - Has an abstract.
ER  -

TY  - JOUR
TI  - Not in PubMed Central
AN  - WOS:000123456700001
UR  - https://www.tandfonline.com/doi/full/10.1080/1350293X.2023.2214714
N1  - Not in PubMed Central; abstract not included
AB  - Has an abstract.
ER  -
"""


def test_ris_import_reads_pmid_and_pmcid(auth_as, a_project, session, monkeypatch):
    _use_test_session(session, monkeypatch)
    client, user = auth_as()
    project = a_project(user)

    assert _upload(client, project, IDENTIFIERS_RIS).status_code == 200

    session.expire_all()
    articles = session.exec(select(Article).where(Article.project_id == project.id))
    assert {a.title: (a.pmid, a.pmcid) for a in articles} == {
        "Prefixed PMID with the PMCID in a note": ("31963506", "PMC7014402"),
        "PMCID only in the link": (None, "PMC8150277"),
        "PMCID in C2": ("31835477", "PMC6950277"),
        # Another database's accession number is not stored as a PMID
        "Not in PubMed Central": (None, None),
    }
