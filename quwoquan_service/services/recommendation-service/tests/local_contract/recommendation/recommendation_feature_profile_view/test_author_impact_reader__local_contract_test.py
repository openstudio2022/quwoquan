import pytest

from internal.recommendation.recommendation_feature_profile_view.application.author_impact_reader import (
    AuthorImpactEvidencePage,
    AuthorImpactSummary,
    Reader,
)


class _Store:
    def __init__(self) -> None:
        self.summary_args = None
        self.evidence_args = None

    def read_author_impact(self, author_id: str, limit: int) -> AuthorImpactSummary:
        self.summary_args = (author_id, limit)
        return AuthorImpactSummary(author_id=author_id, total=0, items=())

    def read_author_impact_evidence(
        self,
        author_id: str,
        impact_id: str,
        cursor: str | None,
        limit: int,
    ) -> AuthorImpactEvidencePage:
        self.evidence_args = (author_id, impact_id, cursor, limit)
        return AuthorImpactEvidencePage(
            impact_id=impact_id,
            total_count=0,
            items=(),
            next_cursor=None,
            has_more=False,
        )


def test_reader_normalizes_author_impact_queries() -> None:
    store = _Store()
    reader = Reader(store)
    assert reader.get_author_impact(author_id=" author-001 ").author_id == "author-001"
    assert store.summary_args == ("author-001", 12)
    page = reader.list_author_impact_evidence(
        author_id=" author-001 ",
        impact_id=" impact-001 ",
        cursor=" cursor-001 ",
        limit=25,
    )
    assert page.impact_id == "impact-001"
    assert store.evidence_args == (
        "author-001",
        "impact-001",
        "cursor-001",
        25,
    )


@pytest.mark.parametrize(
    ("author_id", "impact_id", "limit"),
    (("", "impact-001", 20), ("author-001", "", 20), ("author-001", "impact-001", 0)),
)
def test_reader_rejects_invalid_evidence_queries(
    author_id: str,
    impact_id: str,
    limit: int,
) -> None:
    with pytest.raises(ValueError, match="query is invalid"):
        Reader(_Store()).list_author_impact_evidence(
            author_id=author_id,
            impact_id=impact_id,
            limit=limit,
        )
