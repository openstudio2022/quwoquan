package local_contract

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

type operationIntersectionSource struct {
	facts  []intersectionapp.IntersectionReasonView
	object []intersectionapp.IntersectionReasonView
}

func (s operationIntersectionSource) FactReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	out := make([]intersectionapp.IntersectionReasonView, len(s.facts))
	copy(out, s.facts)
	return out, nil
}

func (s operationIntersectionSource) AffinityReasons(context.Context, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	return nil, nil
}

func (s operationIntersectionSource) ObjectReasons(context.Context, string, string, string) ([]intersectionapp.IntersectionReasonView, error) {
	out := make([]intersectionapp.IntersectionReasonView, len(s.object))
	copy(out, s.object)
	return out, nil
}

func newContractRouter(t *testing.T) *rtredis.Router {
	t.Helper()
	router := rtredis.MustNewRouter(rtredis.DefaultRouterConfig())
	t.Cleanup(func() { _ = router.Close() })
	return router
}

func contractDisplayReadyReason(
	id, sourceRef, dimension, targetID, objectKind, displayName string,
	strength float64,
	freshAt string,
) intersectionapp.IntersectionReasonView {
	actorID := "actor_" + id
	return intersectionapp.IntersectionReasonView{
		IntersectionID:            id,
		IntersectionClass:         "fact",
		Kind:                      sourceRef,
		Dimension:                 dimension,
		ObjectKind:                objectKind,
		ActionTargetID:            targetID,
		DisplayName:               displayName,
		AvatarURL:                 "https://static.quwoquan.test/" + id + ".png",
		Strength:                  strength,
		FreshAt:                   freshAt,
		ActorEvidenceTotalCount:   1,
		ActorEvidenceCompleteness: "complete",
		ActorEvidence: []intersectionapp.IntersectionActorEvidenceView{{
			ActorID:       actorID,
			DisplayName:   "林清越",
			RelationLabel: "你关注的人",
			SourceRef:     sourceRef,
			PrivacyState:  "visible",
			Target: &intersectionapp.IntersectionTargetView{
				ObjectType: "user",
				ObjectID:   actorID,
				ObjectKind: "person",
				RouteID:    "userProfile",
			},
		}},
		IntersectionPoints: []intersectionapp.IntersectionPointView{{
			PointID:    "pt_" + id,
			PointClass: "fact",
			Dimension:  dimension,
			SourceRef:  sourceRef,
			Visibility: "public",
			Count:      1,
		}},
	}
}

func TestIntersectionService_SummaryNewCountAndVisitClears(t *testing.T) {
	ctx := context.Background()
	freshAt := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	source := operationIntersectionSource{
		facts: []intersectionapp.IntersectionReasonView{
			contractDisplayReadyReason("ix_summary_a", "sharedFollowees", "identity", "u1", "person", "林清越", 0.9, freshAt),
			contractDisplayReadyReason("ix_summary_b", "commonFollower", "identity", "u2", "person", "周屿", 0.8, freshAt),
			contractDisplayReadyReason("ix_summary_c", "coCommented", "content", "p1", "content", "摄影路线", 0.7, freshAt),
		},
	}
	svc := intersectionapp.NewIntersectionService(newContractRouter(t), intersectionapp.WithIntersectionSource(source))

	summary, err := svc.Summary(ctx, "viewer_summary_contract")
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if summary.TotalCount != 3 || summary.TotalNewCount != 3 {
		t.Fatalf("unexpected initial summary: %+v", summary)
	}

	if err := svc.MarkVisited(ctx, "viewer_summary_contract", "identity"); err != nil {
		t.Fatalf("mark visited: %v", err)
	}
	after, err := svc.Summary(ctx, "viewer_summary_contract")
	if err != nil {
		t.Fatalf("summary after visit: %v", err)
	}
	if after.TotalCount != 3 || after.TotalNewCount != 1 {
		t.Fatalf("unexpected summary after visit: %+v", after)
	}
}

func TestIntersectionService_ListFiltersAndPaginates(t *testing.T) {
	freshAt := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	relationA := contractDisplayReadyReason("ix_list_a", "sharedFollowees", "relationship", "u1", "person", "林清越", 0.9, freshAt)
	relationA.TimeBucket = "today"
	relationB := contractDisplayReadyReason("ix_list_b", "commonFollower", "relationship", "u2", "person", "周屿", 0.8, freshAt)
	relationB.TimeBucket = "today"
	content := contractDisplayReadyReason("ix_list_c", "coCommented", "content", "p1", "content", "摄影路线", 0.7, freshAt)
	content.TimeBucket = "last7Days"
	source := operationIntersectionSource{
		facts: []intersectionapp.IntersectionReasonView{relationA, relationB, content},
	}
	svc := intersectionapp.NewIntersectionService(newContractRouter(t), intersectionapp.WithIntersectionSource(source))

	page, nextCursor, hasMore, err := svc.List(context.Background(), "viewer_list_contract", intersectionapp.IntersectionListQuery{
		Dimension:  "relationship",
		TimeBucket: "today",
		Limit:      1,
	})
	if err != nil {
		t.Fatalf("list page: %v", err)
	}
	if len(page) != 1 || page[0].IntersectionID != "ix_list_a" || !hasMore || nextCursor == "" {
		t.Fatalf("unexpected page: items=%+v next=%q hasMore=%v", page, nextCursor, hasMore)
	}
}

func TestIntersectionService_ObjectIntersectionsRanksByAnchorStrength(t *testing.T) {
	freshAt := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	reason := contractDisplayReadyReason(
		"ix_object_u_lin",
		"sharedFollowees",
		"relationship",
		"u_lin",
		"person",
		"林清越",
		0.9,
		freshAt,
	)
	reason.RelationObjectID = "u_lin"
	reason.IntersectionPoints = []intersectionapp.IntersectionPointView{
		{PointID: "p_content", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同讨论过", DisplayText: "共同讨论过", Count: 3, Visibility: "public"},
		{PointID: "p_affinity", PointClass: "recommended", Dimension: "interest", SourceRef: "affinity", Label: "可能合得来", DisplayText: "可能合得来", Visibility: "public"},
		{PointID: "p_friend", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", DisplayText: "共同关注的人", Count: 4, Visibility: "public"},
	}
	source := operationIntersectionSource{
		object: []intersectionapp.IntersectionReasonView{reason},
	}
	svc := intersectionapp.NewIntersectionService(newContractRouter(t), intersectionapp.WithIntersectionSource(source))

	items, err := svc.ObjectIntersections(context.Background(), "viewer_object_contract", "u_lin", "user", 8)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("want one object intersection, got %+v", items)
	}
	points := items[0].IntersectionPoints
	if len(points) != 3 {
		t.Fatalf("want three points, got %+v", points)
	}
	if points[0].SourceRef != "sharedFollowees" || points[1].SourceRef != "coCommented" || points[2].SourceRef != "affinity" {
		t.Fatalf("unexpected anchor order: %+v", points)
	}
}
