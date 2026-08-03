// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

func TestTripPlanRevisionIsImmutableValidatedAndAppendedThroughItsOwnPort(t *testing.T) {
	port := &revisionAppender{}
	appender := application.NewAppender(port)
	revision, err := model.Create(model.CreateInput{
		RevisionID: "trv_1", TripID: "trip_1", RevisionNumber: 1,
		ChangeReason: "initial_plan", Severity: model.SeverityImportant,
		Items: []model.ItemSnapshot{{
			ItemID: "west-lake", DayIndex: 0, OrderInDay: 0,
			Kind: "sight", Title: "西湖",
		}},
		Changes:            model.InitialChanges([]model.ItemSnapshot{{ItemID: "west-lake", DayIndex: 0, OrderInDay: 0, Kind: "sight", Title: "西湖"}}),
		AffectedPersonaIDs: []string{"persona-organizer"},
		CreatedByPersonaID: "persona-organizer",
		CreatedAt:          time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := appender.Append(t.Context(), revision); err != nil {
		t.Fatal(err)
	}
	if port.appended.RevisionID != revision.RevisionID || len(port.appended.Items) != 1 {
		t.Fatalf("appended=%+v", port.appended)
	}
	invalid := revision
	invalid.RevisionNumber = 0
	if err := appender.Append(t.Context(), invalid); !errors.Is(err, model.ErrInvalidRevision) {
		t.Fatalf("invalid revision err=%v", err)
	}
}

func TestTripPlanRevisionDiffUsesStableItemIdentity(t *testing.T) {
	previous := []model.ItemSnapshot{
		{ItemID: "hotel", DayIndex: 0, OrderInDay: 0, Kind: "stay", Title: "入住一晚"},
		{ItemID: "dinner", DayIndex: 0, OrderInDay: 1, Kind: "food", Title: "晚餐"},
	}
	next := []model.ItemSnapshot{
		{ItemID: "hotel", DayIndex: 0, OrderInDay: 0, Kind: "stay", Title: "入住两晚"},
		{ItemID: "museum", DayIndex: 0, OrderInDay: 1, Kind: "sight", Title: "博物馆"},
	}
	changes := model.DiffItems(previous, next)
	if len(changes) != 3 {
		t.Fatalf("changes=%+v", changes)
	}
	want := map[model.ChangeKind]bool{
		model.ChangeItemAdded: true, model.ChangeItemRemoved: true, model.ChangeItemUpdated: true,
	}
	for _, change := range changes {
		delete(want, change.Kind)
	}
	if len(want) != 0 {
		t.Fatalf("missing change kinds=%v", want)
	}
}

type revisionAppender struct {
	appended model.Revision
}

func (port *revisionAppender) AppendInTripPlanTransaction(
	_ context.Context,
	revision model.Revision,
) error {
	port.appended = revision
	return nil
}
