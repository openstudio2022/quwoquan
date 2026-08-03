// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
package trip_plan_placement_test

import (
	"context"
	"fmt"
	"sync/atomic"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripPlanPlacementMongoReturnsAllActiveTripsOnOneSurface(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_plan_placement_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	authority := placementAuthority{}
	service := application.NewService(store, authority, authority, authority, &placementIDs{}, time.Now)
	for index, tripID := range []string{"trip_1", "trip_2"} {
		result, err := service.Put(t.Context(), application.PutCommand{
			ActorPersonaID: "persona_owner", IdempotencyKey: "placement-put-" + tripID,
			TripID: tripID, SurfaceKind: model.SurfaceConversation,
			SurfaceID: "conversation_shared", SourceVersion: 7,
		})
		if err != nil || result.Placement.Version != 1 || result.Placement.TripID != tripID {
			t.Fatalf("Put(%d)=%+v err=%v", index, result, err)
		}
	}
	placements, err := service.ListBySurface(t.Context(), "persona_member", model.SurfaceConversation, "conversation_shared")
	if err != nil || len(placements) != 2 {
		t.Fatalf("ListBySurface()=%+v err=%v", placements, err)
	}
	travelsupport.Count(t, database.Collection("trip_plan_placements"), bson.M{"status": model.StatusActive}, 2)
	travelsupport.Count(t, database.Collection("trip_plan_placement_command_receipts"), bson.M{}, 2)
	travelsupport.Count(t, database.Collection("trip_plan_placement_outbox"), bson.M{}, 2)
}

type placementAuthority struct{}

func (placementAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "persona_owner", nil
}
func (placementAuthority) CanViewTrip(context.Context, string, string) error { return nil }
func (placementAuthority) RequireAdmin(context.Context, model.SurfaceKind, string, string, int64) error {
	return nil
}
func (placementAuthority) RequireMember(context.Context, model.SurfaceKind, string, string) error {
	return nil
}

type placementIDs struct{ next atomic.Int64 }

func (ids *placementIDs) NewTripPlanPlacementID() (string, error) {
	return fmt.Sprintf("tpl_%d", ids.next.Add(1)), nil
}
func (ids *placementIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tev_%d", ids.next.Add(1)), nil
}
