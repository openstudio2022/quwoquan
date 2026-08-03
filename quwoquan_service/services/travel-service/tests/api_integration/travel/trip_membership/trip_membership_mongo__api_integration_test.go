// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
package trip_membership_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripMembershipMongoCommitsStateReceiptAndOutbox(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_membership_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	service := application.NewService(store, membershipTripAuthority{}, application.NewSourceAuthority(nil), membershipIDs{}, time.Now)
	result, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "persona_owner", IdempotencyKey: "membership-put", TripID: "trip_1",
		PersonaID: "persona_member", Role: model.RoleParticipant,
		SourceKind: model.SourceTripInvitation,
	})
	if err != nil || result.Membership.Version != 1 {
		t.Fatalf("Put()=%+v err=%v", result, err)
	}
	if replay, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "persona_owner", IdempotencyKey: "membership-put", TripID: "trip_1",
		PersonaID: "persona_member", Role: model.RoleParticipant,
		SourceKind: model.SourceTripInvitation,
	}); err != nil || !replay.IdempotentReplay {
		t.Fatalf("replay=%+v err=%v", replay, err)
	}
	travelsupport.Count(t, database.Collection("trip_memberships"), bson.M{"tripId": "trip_1"}, 1)
	travelsupport.Count(t, database.Collection("trip_membership_command_receipts"), bson.M{}, 1)
	travelsupport.Count(t, database.Collection("trip_membership_outbox"), bson.M{}, 1)
}

type membershipTripAuthority struct{}

func (membershipTripAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "persona_owner", nil
}

type membershipIDs struct{}

func (membershipIDs) NewTripMembershipID() (string, error) { return "tpm_member", nil }
func (membershipIDs) NewEventID() (string, error)          { return "tev_member", nil }
