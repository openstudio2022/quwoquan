// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_guide_assignment_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripGuideAssignmentMongoCommitsTaskLifecycleReceiptAndOutbox(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_guide_assignment_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	authority := guideAuthority{}
	service := application.NewService(store, authority, authority, application.NewPersonaAuthority(nil), &guideIDs{}, time.Now)
	created, err := service.Put(t.Context(), application.PutCommand{ActorPersonaID: "persona_owner", IdempotencyKey: "guide-put", TripID: "trip_1", TaskKey: "meeting", Input: model.PutInput{AssigneePersonaID: "persona_assistant", Role: model.RoleAssistantGuide, TaskKind: model.TaskCollection, Title: "集合成员", SourceRevisionNumber: 2, AttributionKind: model.AttributionAdministrative, AttributionPersonaID: "persona_assistant"}})
	if err != nil || created.Assignment.Version != 1 {
		t.Fatalf("Put()=%+v err=%v", created, err)
	}
	accepted, err := service.Transition(t.Context(), application.TransitionCommand{ActorPersonaID: "persona_assistant", IdempotencyKey: "guide-accept", TripID: "trip_1", TaskKey: "meeting", ExpectedVersion: 1, TargetStatus: model.StatusAccepted})
	if err != nil || accepted.Assignment.Status != model.StatusAccepted {
		t.Fatalf("Transition()=%+v err=%v", accepted, err)
	}
	travelsupport.Count(t, database.Collection("trip_guide_assignments"), bson.M{"tripId": "trip_1", "taskKey": "meeting"}, 1)
	travelsupport.Count(t, database.Collection("trip_guide_assignment_command_receipts"), bson.M{}, 2)
	travelsupport.Count(t, database.Collection("trip_guide_assignment_outbox"), bson.M{}, 2)
}

type guideAuthority struct{}

func (guideAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "persona_owner", nil
}

func (guideAuthority) CanViewTrip(context.Context, string, string) error { return nil }

type guideIDs struct{ next int }

func (ids *guideIDs) NewTripGuideAssignmentID() (string, error) {
	ids.next++
	return "tga_1", nil
}

func (ids *guideIDs) NewEventID() (string, error) {
	ids.next++
	if ids.next == 2 {
		return "tev_guide_put", nil
	}
	return "tev_guide_transition", nil
}
