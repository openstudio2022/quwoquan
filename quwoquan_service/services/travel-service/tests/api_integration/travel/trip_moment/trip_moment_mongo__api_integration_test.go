// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
package trip_moment_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripMomentMongoCommitsMomentReceiptAndOutbox(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_moment_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	authority := momentAuthority{}
	service := application.NewService(store, authority, authority, authority, authority, momentIDs{}, time.Now)
	result, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "persona_member", IdempotencyKey: "moment-create", TripID: "trip_1",
		RevisionNumber: 1, Kind: model.KindText, InlineText: "西湖边的风很舒服",
		CapturedAt: time.Date(2026, 8, 2, 11, 0, 0, 0, time.UTC),
		Visibility: model.VisibilityTripMembers, AssignmentStatus: model.AssignmentUnassigned,
	})
	if err != nil || result.Moment.Version != 1 {
		t.Fatalf("Create()=%+v err=%v", result, err)
	}
	moments, err := service.List(t.Context(), "persona_member", "trip_1")
	if err != nil || len(moments) != 1 || moments[0].InlineText == "" {
		t.Fatalf("List()=%+v err=%v", moments, err)
	}
	travelsupport.Count(t, database.Collection("trip_moments"), bson.M{"tripId": "trip_1"}, 1)
	travelsupport.Count(t, database.Collection("trip_moment_command_receipts"), bson.M{}, 1)
	travelsupport.Count(t, database.Collection("trip_moment_outbox"), bson.M{}, 1)
}

type momentAuthority struct{}

func (momentAuthority) CanViewTrip(context.Context, string, string) error { return nil }
func (momentAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "persona_owner", nil
}
func (momentAuthority) ValidateAssignment(context.Context, string, int64, int, string) error {
	return nil
}
func (momentAuthority) ValidateMomentReferences(context.Context, model.Kind, *model.ObjectRef, *model.ObjectRef, string) error {
	return nil
}

type momentIDs struct{}

func (momentIDs) NewTripMomentID() (string, error) { return "tmo_moment", nil }
func (momentIDs) NewEventID() (string, error)      { return "tev_moment", nil }
