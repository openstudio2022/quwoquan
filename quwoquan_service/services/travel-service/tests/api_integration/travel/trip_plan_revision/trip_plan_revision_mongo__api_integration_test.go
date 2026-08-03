// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package trip_plan_revision_test

import (
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripPlanRevisionMongoPersistsImmutableNumberedSnapshot(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_revision_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	revision, err := model.Create(model.CreateInput{
		RevisionID: "trv_1", TripID: "trip_1", RevisionNumber: 1,
		ChangeReason: "initial_plan", Severity: model.SeverityImportant,
		Items:              []model.ItemSnapshot{{ItemID: "item_west_lake", DayIndex: 0, OrderInDay: 0, Kind: "sight", Title: "西湖"}},
		Changes:            model.InitialChanges([]model.ItemSnapshot{{ItemID: "item_west_lake", DayIndex: 0, OrderInDay: 0, Kind: "sight", Title: "西湖"}}),
		AffectedPersonaIDs: []string{"persona_owner"}, CreatedByPersonaID: "persona_owner",
		CreatedAt: time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := application.NewAppender(store).Append(t.Context(), revision); err != nil {
		t.Fatal(err)
	}
	actual, err := application.NewReader(store).Get(t.Context(), "trip_1", 1)
	if err != nil || actual.RevisionID != "trv_1" || len(actual.Items) != 1 {
		t.Fatalf("Get()=%+v err=%v", actual, err)
	}
	travelsupport.Count(t, database.Collection("trip_plan_revisions"), bson.M{"tripId": "trip_1", "revisionNumber": int64(1)}, 1)
}
