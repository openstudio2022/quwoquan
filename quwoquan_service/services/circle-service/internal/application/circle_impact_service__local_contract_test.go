package application

import (
	"context"
	"testing"

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
	if got.CircleID != "circle_1" {
		t.Fatalf("circleId = %v", got.CircleID)
	}
	if len(got.Items) != 1 {
		t.Fatalf("items len = %d", len(got.Items))
	}
	if got.Items[0].PrimaryText != "契约摄影社主理人等12人加入了契约摄影社" {
		t.Fatalf("primaryText = %q", got.Items[0].PrimaryText)
	}
	if got.Items[0].RepresentativeActor == nil || got.Items[0].RepresentativeActor.Target == nil || got.Items[0].RepresentativeActor.Target.ObjectType != "user" {
		t.Fatalf("representativeActor = %+v", got.Items[0].RepresentativeActor)
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
	if len(got.Items) != 0 {
		t.Fatalf("items len = %d", len(got.Items))
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
	if len(got.Items) != 0 {
		t.Fatalf("items must fail closed, got %#v", got.Items)
	}
}

func TestGetCircleStatsReturnsTypedWire(t *testing.T) {
	store := fakeCircleStore{circles: map[string]*model.Circle{
		"circle_1": {
			ID: "circle_1", MemberCount: 12, WeeklyActiveCount: 3, PostCount: 5,
			StorageUsedBytes: 1024, StorageQuotaBytes: 2048,
		},
	}}
	service := NewCircleService(fakeCircleStorage(store))

	stats, err := service.GetCircleStats(context.Background(), "circle_1")
	if err != nil {
		t.Fatalf("GetCircleStats returned error: %v", err)
	}
	if stats.TotalMembers != 12 || stats.WeeklyActive != 3 || stats.TotalPosts != 5 ||
		stats.StorageUsedBytes != 1024 || stats.StorageQuotaBytes != 2048 {
		t.Fatalf("stats wire drift: %+v", stats)
	}
	if _, err := service.GetCircleStats(context.Background(), "missing"); err == nil {
		t.Fatal("missing circle stats must fail closed")
	}
}

type fakeCircleStore struct {
	circles map[string]*model.Circle
}

func fakeCircleStorage(store fakeCircleStore) CircleStoragePorts {
	return CircleStoragePorts{Records: store}
}

func (s fakeCircleStore) FindByID(_ context.Context, id string) (*model.Circle, bool) {
	c, ok := s.circles[id]
	return c, ok
}

func (s fakeCircleStore) List(context.Context, ListCirclesQuery) ([]model.Circle, string) {
	return nil, ""
}
