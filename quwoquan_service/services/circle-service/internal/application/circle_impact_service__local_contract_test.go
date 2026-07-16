package application

import (
	"context"
	"errors"
	"testing"

	rtimpact "quwoquan_service/runtime/impact"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

func TestGetCircleImpactReturnsTopFacts(t *testing.T) {
	store := fakeCircleStore{
		circles: map[string]*model.Circle{
			"circle_1": {
				ID:                       "circle_1",
				Name:                     "契约摄影社",
				OwnerID:                  "owner_1",
				OwnerDisplayNameSnapshot: "契约摄影社主理人",
				MemberCount:              12,
				PostCount:                5,
				WeeklyActiveCount:        3,
			},
		},
	}
	service := NewCircleService(fakeCircleStorage(store))

	got, err := service.GetCircleImpact(context.Background(), "circle_1")
	if err != nil {
		t.Fatalf("GetCircleImpact returned error: %v", err)
	}
	if got["circleId"] != "circle_1" {
		t.Fatalf("circleId = %v", got["circleId"])
	}
	items, ok := got["items"].([]rtimpact.Statement)
	if !ok {
		t.Fatalf("items type = %T", got["items"])
	}
	if len(items) != 1 {
		t.Fatalf("items len = %d", len(items))
	}
	if items[0].PrimaryText != "契约摄影社主理人等12人加入了契约摄影社" {
		t.Fatalf("primaryText = %q", items[0].PrimaryText)
	}
	if items[0].RepresentativeActor == nil || items[0].RepresentativeActor.Target == nil || items[0].RepresentativeActor.Target.ObjectType != "user" {
		t.Fatalf("representativeActor = %+v", items[0].RepresentativeActor)
	}
}

func TestGetCircleImpactEmptyCircleReturnsEmptyItems(t *testing.T) {
	store := fakeCircleStore{
		circles: map[string]*model.Circle{
			"empty": {ID: "empty"},
		},
	}
	service := NewCircleService(fakeCircleStorage(store))

	got, err := service.GetCircleImpact(context.Background(), "empty")
	if err != nil {
		t.Fatalf("GetCircleImpact returned error: %v", err)
	}
	items, ok := got["items"].([]rtimpact.Statement)
	if !ok {
		t.Fatalf("items type = %T", got["items"])
	}
	if len(items) != 0 {
		t.Fatalf("items len = %d", len(items))
	}
}

func TestGetCircleImpactCountWithoutActorEvidenceFailsClosed(t *testing.T) {
	store := fakeCircleStore{circles: map[string]*model.Circle{
		"no_actor": {ID: "no_actor", Name: "无证据圈子", OwnerID: "owner_1", MemberCount: 99},
	}}
	service := NewCircleService(fakeCircleStorage(store))

	got, err := service.GetCircleImpact(context.Background(), "no_actor")
	if err != nil {
		t.Fatalf("GetCircleImpact returned error: %v", err)
	}
	items, ok := got["items"].([]rtimpact.Statement)
	if !ok || len(items) != 0 {
		t.Fatalf("items must fail closed, got %#v", got["items"])
	}
}

func TestPinAndFeaturePostPersistThroughFeedStore(t *testing.T) {
	feed := &fakeFeedStore{ok: true}
	service := NewCircleService(fakeCircleStorage(fakeCircleStore{}), WithFeedStore(feed))

	if err := service.PinPost(context.Background(), "circle_1", "post_1", true); err != nil {
		t.Fatalf("PinPost returned error: %v", err)
	}
	if feed.pinnedCircleID != "circle_1" || feed.pinnedPostID != "post_1" || !feed.pinned {
		t.Fatalf("pin call not persisted through feed store: %#v", feed)
	}

	if err := service.FeaturePost(context.Background(), "circle_1", "post_1", true); err != nil {
		t.Fatalf("FeaturePost returned error: %v", err)
	}
	if feed.featuredCircleID != "circle_1" || feed.featuredPostID != "post_1" || !feed.featured {
		t.Fatalf("feature call not persisted through feed store: %#v", feed)
	}
}

func TestPinPostNotFoundReturnsError(t *testing.T) {
	service := NewCircleService(fakeCircleStorage(fakeCircleStore{}), WithFeedStore(&fakeFeedStore{}))

	err := service.PinPost(context.Background(), "circle_1", "missing_post", true)
	if err == nil {
		t.Fatal("expected error for missing circle post")
	}
}

func TestFeaturePostStoreErrorReturnsError(t *testing.T) {
	service := NewCircleService(fakeCircleStorage(fakeCircleStore{}), WithFeedStore(&fakeFeedStore{err: errors.New("mongo down")}))

	err := service.FeaturePost(context.Background(), "circle_1", "post_1", true)
	if err == nil {
		t.Fatal("expected error for feed store failure")
	}
}

type fakeCircleStore struct {
	circles map[string]*model.Circle
}

func fakeCircleStorage(store fakeCircleStore) CircleStoragePorts {
	return CircleStoragePorts{
		Records: store, Metrics: store, Sections: store,
		IDs: fakeEntityIDGenerator{},
	}
}

type fakeEntityIDGenerator struct{}

func (fakeEntityIDGenerator) NewID() string { return "test_generated_id" }

func (s fakeCircleStore) Create(context.Context, *model.Circle) error { return nil }

func (s fakeCircleStore) Update(context.Context, string, *model.Circle) bool {
	return true
}

func (s fakeCircleStore) FindByID(_ context.Context, id string) (*model.Circle, bool) {
	c, ok := s.circles[id]
	return c, ok
}

func (s fakeCircleStore) List(context.Context, ListCirclesQuery) ([]model.Circle, string) {
	return nil, ""
}

func (s fakeCircleStore) Archive(context.Context, string) bool { return true }

func (s fakeCircleStore) UpdateWeeklyActiveCount(context.Context, string, int64) error {
	return nil
}

func (s fakeCircleStore) UpdateStorageUsed(context.Context, string, int64) error {
	return nil
}

func (s fakeCircleStore) UpdateSections(context.Context, string, []model.CircleSectionConfig) error {
	return nil
}

type fakeFeedStore struct {
	ok  bool
	err error

	pinnedCircleID string
	pinnedPostID   string
	pinned         bool

	featuredCircleID string
	featuredPostID   string
	featured         bool
}

func (s *fakeFeedStore) ListCirclePosts(context.Context, string, ListCirclePostsQuery) ([]map[string]any, string) {
	return nil, ""
}

func (s *fakeFeedStore) UpdateCirclePostPinned(_ context.Context, circleID, postID string, pinned bool) (bool, error) {
	s.pinnedCircleID = circleID
	s.pinnedPostID = postID
	s.pinned = pinned
	return s.ok, s.err
}

func (s *fakeFeedStore) UpdateCirclePostFeatured(_ context.Context, circleID, postID string, featured bool) (bool, error) {
	s.featuredCircleID = circleID
	s.featuredPostID = postID
	s.featured = featured
	return s.ok, s.err
}
