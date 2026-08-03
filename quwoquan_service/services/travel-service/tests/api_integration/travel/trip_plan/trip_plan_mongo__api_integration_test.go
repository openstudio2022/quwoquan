// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package api_integration

import (
	"context"
	"fmt"
	"sync/atomic"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/persistence"
	revisiontransaction "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/adapters/inbound/transaction"
	revisionapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/application"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	revisionpersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/infrastructure/persistence"
)

// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-002
func TestTripPlanMongoTransactionCommitsPlanRevisionReceiptOutboxAndStableList(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "travel_trip_plan_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	revisionStore := revisionpersistence.NewMongoStore(runtime.Database)
	if err := revisionStore.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure TripPlanRevision indexes: %v", err)
	}
	store := persistence.NewMongoStore(
		runtime.Database,
		revisiontransaction.NewAppender(revisionapplication.NewAppender(revisionStore)),
	)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure TripPlan indexes: %v", err)
	}
	service := application.NewService(
		store, revisionapplication.NewReader(revisionStore), nil, &mongoTestIDs{}, time.Now,
	)
	created, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "persona-trip-owner", IdempotencyKey: "create-trip", Title: "杭州七日游",
		Items: []application.ItemInput{
			{ItemID: "hotel", DayIndex: 0, OrderInDay: 0, Kind: model.ItemStay, Title: "入住"},
			{ItemID: "dinner", DayIndex: 0, OrderInDay: 1, Kind: model.ItemFood, Title: "晚餐"},
		},
	})
	if err != nil {
		t.Fatalf("Create(): %v", err)
	}
	if _, err := service.Revise(t.Context(), application.ReviseCommand{
		ActorPersonaID: "persona-trip-owner", IdempotencyKey: "revise-trip", TripID: created.TripID,
		ExpectedRevisionNumber: 1, ChangeReason: "晚餐延后", Severity: revisionmodel.SeverityImportant,
		Items: []application.ItemInput{
			{ItemID: "hotel", DayIndex: 0, OrderInDay: 0, Kind: model.ItemStay, Title: "入住"},
			{ItemID: "dinner", DayIndex: 0, OrderInDay: 1, Kind: model.ItemFood, Title: "晚餐改到八点"},
		},
	}); err != nil {
		t.Fatalf("Revise(): %v", err)
	}
	second, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "persona-trip-owner", IdempotencyKey: "create-trip-second", Title: "杭州周末游",
		Items: []application.ItemInput{{ItemID: "lake", DayIndex: 1, OrderInDay: 1, Kind: model.ItemSight, Title: "西湖"}},
	})
	if err != nil {
		t.Fatalf("Create(second): %v", err)
	}
	foreign, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "persona-other", IdempotencyKey: "create-trip-foreign", Title: "不应泄漏",
		Items: []application.ItemInput{},
	})
	if err != nil {
		t.Fatalf("Create(foreign): %v", err)
	}
	firstPage, err := service.List(t.Context(), application.ListQuery{
		ActorPersonaID: "persona-trip-owner", Limit: 1,
	})
	if err != nil || len(firstPage.Plans) != 1 || firstPage.NextCursor == "" {
		t.Fatalf("first page=%+v err=%v", firstPage, err)
	}
	secondPage, err := service.List(t.Context(), application.ListQuery{
		ActorPersonaID: "persona-trip-owner", Limit: 1, Cursor: firstPage.NextCursor,
	})
	if err != nil || len(secondPage.Plans) != 1 ||
		secondPage.Plans[0].TripID == firstPage.Plans[0].TripID ||
		secondPage.Plans[0].TripID == foreign.TripID {
		t.Fatalf("second page=%+v err=%v", secondPage, err)
	}
	listed := map[string]bool{
		firstPage.Plans[0].TripID:  true,
		secondPage.Plans[0].TripID: true,
	}
	if !listed[created.TripID] || !listed[second.TripID] || listed[foreign.TripID] {
		t.Fatalf("organizer-scoped list=%v", listed)
	}
	if _, err := service.List(t.Context(), application.ListQuery{
		ActorPersonaID: "persona-trip-owner", Limit: 1, Cursor: "not-a-cursor",
	}); err == nil {
		t.Fatal("invalid cursor must fail closed")
	}

	assertMongoCount(t, runtime.Database.Collection("trip_plans"), bson.M{"_id": created.TripID, "currentRevisionNumber": int64(2)}, 1)
	assertMongoCount(t, runtime.Database.Collection("trip_plan_revisions"), bson.M{"tripId": created.TripID}, 2)
	assertMongoCount(t, runtime.Database.Collection("trip_plan_command_receipts"), bson.M{"tripId": created.TripID}, 2)
	assertMongoCount(t, runtime.Database.Collection("trip_plan_outbox"), bson.M{"aggregateId": created.TripID}, 2)
}

type mongoTestIDs struct{ value atomic.Int64 }

func (generator *mongoTestIDs) NewTripPlanID() (string, error) {
	return fmt.Sprintf("trip_%d", generator.value.Add(1)), nil
}

func (generator *mongoTestIDs) NewRevisionID() (string, error) {
	return fmt.Sprintf("trv_%d", generator.value.Add(1)), nil
}

func (generator *mongoTestIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_%d", generator.value.Add(1)), nil
}

func assertMongoCount(t *testing.T, collection *mongo.Collection, filter any, expected int64) {
	t.Helper()
	count, err := collection.CountDocuments(t.Context(), filter)
	if err != nil || count != expected {
		t.Fatalf("Mongo count=%d want=%d err=%v filter=%#v", count, expected, err, filter)
	}
}
