"""GET /articles filter for records closed by the stopping rule, and score sorting."""

from app.features.research.models import ArticleStatus, FinalDecision
from app.features.screening.models import ScreeningStage

BASE = "api/v1/projects"


def _excluded(an_article_in, project, **kw):
    return an_article_in(
        project,
        status=ArticleStatus.excluded,
        current_stage=ScreeningStage.completed,
        final_decision=FinalDecision.excluded,
        **kw,
    )


def _ids(res):
    assert res.status_code == 200, res.text
    return [a["id"] for a in res.json()["data"]]


def test_list_filters_not_screened_records(auth_as, a_project, an_article_in):
    client, owner = auth_as()
    project = a_project(owner)
    ns = _excluded(
        an_article_in, project, not_screened_stopping_rule=True, relevance_score=0.2
    )
    ex = _excluded(an_article_in, project)
    pend = an_article_in(project)
    url = f"{BASE}/{project.id}/articles"

    res = client.get(f"{url}?not_screened_stopping_rule=true")
    assert _ids(res) == [ns.id]
    item = res.json()["data"][0]
    assert item["not_screened_stopping_rule"] is True
    assert item["relevance_score"] == 0.2
    assert sorted(_ids(client.get(f"{url}?not_screened_stopping_rule=false"))) == [
        ex.id,
        pend.id,
    ]
    res = client.get(f"{url}?status=excluded&not_screened_stopping_rule=false")
    assert _ids(res) == [ex.id]


def test_sort_by_relevance_score_puts_nulls_last(auth_as, a_project, an_article_in):
    client, owner = auth_as()
    project = a_project(owner)
    never = an_article_in(project)
    low = an_article_in(project, relevance_score=0.1)
    high = an_article_in(project, relevance_score=0.9)
    url = f"{BASE}/{project.id}/articles"

    desc = _ids(client.get(f"{url}?sort_by=relevance_score&order=desc"))
    assert desc == [high.id, low.id, never.id]
    asc = _ids(client.get(f"{url}?sort_by=relevance_score&order=asc"))
    assert asc == [low.id, high.id, never.id]
