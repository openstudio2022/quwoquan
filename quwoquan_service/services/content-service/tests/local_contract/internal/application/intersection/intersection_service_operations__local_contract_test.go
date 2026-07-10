package local_contract

import (
	"context"
	"testing"
	"time"

	intersectionapp "quwoquan_service/services/content-service/internal/application/intersection"
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

func TestIntersectionService_SummaryNewCountAndVisitClears(t *testing.T) {
	ctx := context.Background()
	freshAt := time.Now().UTC().Add(-time.Hour).Format(time.RFC3339)
	source := operationIntersectionSource{
		facts: []intersectionapp.IntersectionReasonView{
			contractDisplayReadyReason("ix_summary_a", "sharedFollowees", "identity", "u1", "person", "林清越", 0.9, freshAt),
			contractDisplayReadyReason("ix_summary_b", "commonContact", "identity", "u2", "person", "周屿", 0.8, freshAt),
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
	relationB := contractDisplayReadyReason("ix_list_b", "commonContact", "relationship", "u2", "person", "周屿", 0.8, freshAt)
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
	source := operationIntersectionSource{
		object: []intersectionapp.IntersectionReasonView{
			{
				IntersectionID:   "ix_object_u_lin",
				Dimension:        "relationship",
				ActionTargetID:   "u_lin",
				RelationObjectID: "u_lin",
				IntersectionPoints: []intersectionapp.IntersectionPointView{
					{PointID: "p_content", PointClass: "fact", Dimension: "content", SourceRef: "coCommented", Label: "共同讨论过", DisplayText: "共同讨论过", Count: 3},
					{PointID: "p_affinity", PointClass: "recommended", Dimension: "interest", SourceRef: "affinity", Label: "可能合得来", DisplayText: "可能合得来"},
					{PointID: "p_friend", PointClass: "fact", Dimension: "relationship", SourceRef: "sharedFollowees", Label: "共同关注的人", DisplayText: "共同关注的人", Count: 4},
				},
			},
		},
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
