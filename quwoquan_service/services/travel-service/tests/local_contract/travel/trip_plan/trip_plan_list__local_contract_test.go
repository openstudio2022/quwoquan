// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-002
package local_contract

import (
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
)

func TestTripPlanListIsOrganizerScopedStatusFilteredAndBounded(t *testing.T) {
	store := newMemoryTripStore()
	service := application.NewService(store, store, nil, &sequenceIDs{}, time.Now)
	first, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "list-create-1", Title: "西湖周末",
		Items: []application.ItemInput{{ItemID: "west-lake", Kind: model.ItemSight, Title: "西湖", DayIndex: 1, OrderInDay: 1}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "other", IdempotencyKey: "list-create-other", Title: "不应泄漏",
		Items: []application.ItemInput{},
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Transition(t.Context(), application.TransitionCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "list-activate", TripID: first.TripID,
		ExpectedRevisionNumber: 1, TargetStatus: model.StatusActive,
	}); err != nil {
		t.Fatal(err)
	}
	page, err := service.List(t.Context(), application.ListQuery{
		ActorPersonaID: "organizer", Status: model.StatusActive, Limit: 20,
	})
	if err != nil || len(page.Plans) != 1 || page.Plans[0].OrganizerPersonaID != "organizer" ||
		page.Plans[0].CurrentItemCount != 1 {
		t.Fatalf("page=%+v err=%v", page, err)
	}
	if _, err := service.List(t.Context(), application.ListQuery{
		ActorPersonaID: "organizer", Limit: 51,
	}); !errors.Is(err, model.ErrInvalidInput) {
		t.Fatalf("unbounded list err=%v", err)
	}
}
