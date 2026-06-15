package application

import (
	"context"
	"strings"
	"testing"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

func TestGetCircleImpactReturnsTopFacts(t *testing.T) {
	store := fakeCircleStore{
		circles: map[string]*model.Circle{
			"circle_1": {
				ID:                "circle_1",
				MemberCount:       12,
				PostCount:         5,
				WeeklyActiveCount: 3,
			},
		},
	}
	service := NewCircleService(store, fakeMemberStore{}, fakeFileStore{})

	got, err := service.GetCircleImpact(context.Background(), "circle_1")
	if err != nil {
		t.Fatalf("GetCircleImpact returned error: %v", err)
	}
	if got["circleId"] != "circle_1" {
		t.Fatalf("circleId = %v", got["circleId"])
	}
	items, ok := got["items"].([]map[string]any)
	if !ok {
		t.Fatalf("items type = %T", got["items"])
	}
	if len(items) != 3 {
		t.Fatalf("items len = %d", len(items))
	}
	for _, item := range items {
		text, _ := item["displayText"].(string)
		if strings.TrimSpace(text) == "" {
			t.Fatalf("empty displayText in item: %#v", item)
		}
		if strings.Contains(text, "收藏") || strings.Contains(text, "好友") || strings.Contains(text, "朋友") || strings.Contains(text, "实体") {
			t.Fatalf("displayText contains retired/internal word: %q", text)
		}
	}
}

func TestGetCircleImpactEmptyCircleReturnsEmptyItems(t *testing.T) {
	store := fakeCircleStore{
		circles: map[string]*model.Circle{
			"empty": {ID: "empty"},
		},
	}
	service := NewCircleService(store, fakeMemberStore{}, fakeFileStore{})

	got, err := service.GetCircleImpact(context.Background(), "empty")
	if err != nil {
		t.Fatalf("GetCircleImpact returned error: %v", err)
	}
	items, ok := got["items"].([]map[string]any)
	if !ok {
		t.Fatalf("items type = %T", got["items"])
	}
	if len(items) != 0 {
		t.Fatalf("items len = %d", len(items))
	}
}

type fakeCircleStore struct {
	circles map[string]*model.Circle
}

func (s fakeCircleStore) Create(context.Context, *model.Circle) error { return nil }

func (s fakeCircleStore) Update(context.Context, string, *model.Circle) bool {
	return true
}

func (s fakeCircleStore) FindByID(_ context.Context, id string) (*model.Circle, bool) {
	c, ok := s.circles[id]
	return c, ok
}

func (s fakeCircleStore) List(context.Context, persistence.ListCirclesOpts) ([]model.Circle, string) {
	return nil, ""
}

func (s fakeCircleStore) Archive(context.Context, string) bool { return true }

func (s fakeCircleStore) IncrementMemberCount(context.Context, string, int64) error {
	return nil
}

func (s fakeCircleStore) UpdateStorageUsed(context.Context, string, int64) error {
	return nil
}

func (s fakeCircleStore) UpdateSections(context.Context, string, []model.CircleSectionConfig) error {
	return nil
}

type fakeMemberStore struct{}

func (fakeMemberStore) Create(context.Context, *model.CircleMember) error { return nil }

func (fakeMemberStore) FindByCircleAndUser(context.Context, string, string) (*model.CircleMember, bool) {
	return nil, false
}

func (fakeMemberStore) Delete(context.Context, string, string) bool { return true }

func (fakeMemberStore) UpdateRole(context.Context, string, string, model.CircleMemberRole) bool {
	return true
}

func (fakeMemberStore) ListByCircle(context.Context, string, int, string) ([]model.CircleMember, string) {
	return nil, ""
}

func (fakeMemberStore) ListByUser(context.Context, string, int, string) ([]model.CircleMember, string) {
	return nil, ""
}

type fakeFileStore struct{}

func (fakeFileStore) Create(context.Context, *model.CircleFile) error { return nil }

func (fakeFileStore) FindByID(context.Context, string, string) (*model.CircleFile, bool) {
	return nil, false
}

func (fakeFileStore) Update(context.Context, string, string, *model.CircleFile) bool {
	return true
}

func (fakeFileStore) Delete(context.Context, string, string) bool { return true }

func (fakeFileStore) ListByCircle(context.Context, string, persistence.ListFilesOpts) ([]model.CircleFile, string) {
	return nil, ""
}
