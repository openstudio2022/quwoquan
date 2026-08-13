// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t10
// readiness_case: list-circles-local
// readiness_case: list-circle-discovery-feed-local
// readiness_case: search-circles-local
// readiness_case: get-circle-local
// readiness_case: get-circle-feed-local
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

func TestCircleQueryFacadesExecuteEveryPublicReadOperation(t *testing.T) {
	records := &circleQueryRecordDouble{circles: []model.Circle{{
		ID: "circle-alpha", Name: "Alpha 摄影圈", Status: model.CircleStatusActive,
		Visibility: model.CircleVisibilityPublic,
	}}}
	feed := &circleFeedDouble{items: []app.CircleFeedPost{{
		CircleID: "circle-alpha", PlacementID: "placement-1", PostID: "post-1",
	}}}
	discovery := &circleDiscoveryFeedDouble{slice: app.CircleDiscoveryFeedSlice{
		Circles: []model.Circle{records.circles[0]},
		Items:   append([]app.CircleFeedPost(nil), feed.items...),
	}}
	service := app.NewCircleService(
		app.CircleStoragePorts{Records: records},
		app.WithFeedStore(feed),
		app.WithDiscoveryFeedReader(discovery),
	)

	detail, err := service.GetCircle(context.Background(), "circle-alpha")
	if err != nil || detail.ID != "circle-alpha" {
		t.Fatalf("GetCircle drift: detail=%+v err=%v", detail, err)
	}
	listed := service.ListCircles(context.Background(), app.ListCirclesRequest{
		Category: "interest", Limit: 20,
	})
	if len(listed.Items) != 1 || records.lastList.Category != "interest" || records.lastList.Limit != 20 {
		t.Fatalf("ListCircles drift: result=%+v query=%+v", listed, records.lastList)
	}
	searched := service.SearchCircles(context.Background(), app.SearchCirclesRequest{
		Query: "alpha", Limit: 10,
	})
	if len(searched.Items) != 1 || searched.Items[0].CircleID != "circle-alpha" {
		t.Fatalf("SearchCircles drift: %+v", searched)
	}
	feedSlice, err := service.GetCircleFeed(
		context.Background(), "circle-alpha", 10, "", "latest", "", "",
	)
	if err != nil || len(feedSlice.Items) != 1 || feedSlice.Items[0].PostID != "post-1" {
		t.Fatalf("GetCircleFeed drift: result=%+v err=%v", feedSlice, err)
	}
	discoveryContext := operation.WithContext(context.Background(), operation.Context{
		Actor: operation.ActorContext{PersonaID: "persona-viewer"},
	})
	discoverySlice, err := service.ListCircleDiscoveryFeed(
		discoveryContext,
		app.CircleDiscoveryFeedQuery{
			Scope: app.CircleDiscoveryFeedScopeRecommended, Sort: "latest", Limit: 20,
		},
	)
	if err != nil || len(discoverySlice.Circles) != 1 || discovery.lastQuery.PersonaID != "persona-viewer" {
		t.Fatalf("ListCircleDiscoveryFeed drift: result=%+v query=%+v err=%v", discoverySlice, discovery.lastQuery, err)
	}
}

type circleQueryRecordDouble struct {
	circles  []model.Circle
	lastList app.ListCirclesQuery
}

func (double *circleQueryRecordDouble) FindByID(_ context.Context, id string) (*model.Circle, bool) {
	for index := range double.circles {
		if double.circles[index].ID == id {
			value := double.circles[index]
			return &value, true
		}
	}
	return nil, false
}

func (double *circleQueryRecordDouble) List(
	_ context.Context,
	query app.ListCirclesQuery,
) ([]model.Circle, string) {
	double.lastList = query
	return append([]model.Circle(nil), double.circles...), ""
}

type circleFeedDouble struct {
	items []app.CircleFeedPost
}

func (double *circleFeedDouble) ListCirclePosts(
	_ context.Context,
	_ string,
	_ app.ListCirclePostsQuery,
) ([]app.CircleFeedPost, string, error) {
	return append([]app.CircleFeedPost(nil), double.items...), "", nil
}

type circleDiscoveryFeedDouble struct {
	slice     app.CircleDiscoveryFeedSlice
	lastQuery app.CircleDiscoveryFeedQuery
}

func (double *circleDiscoveryFeedDouble) ListCircleDiscoveryFeed(
	_ context.Context,
	query app.CircleDiscoveryFeedQuery,
) (app.CircleDiscoveryFeedSlice, error) {
	double.lastQuery = query
	return double.slice, nil
}
