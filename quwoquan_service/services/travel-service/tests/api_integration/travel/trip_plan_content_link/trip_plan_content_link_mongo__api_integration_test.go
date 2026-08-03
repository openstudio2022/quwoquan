// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
package trip_plan_content_link_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripPlanContentLinkMongoCommitsReferenceWithoutCopyingPost(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_content_link_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	authority := contentLinkAuthority{}
	service := application.NewService(store, authority, authority, authority, authority, contentLinkIDs{}, time.Now)
	result, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "persona_member", IdempotencyKey: "content-link-put",
		TripID: "trip_1", PostID: "post_1", RevisionNumber: 1,
		TargetKind: model.TargetItem, DayIndex: intPointer(0),
		ItemID: "item_west_lake", Visibility: model.VisibilityPublic, SourceVersion: 4,
	})
	if err != nil || result.Link.PostID != "post_1" || result.Link.Version != 1 {
		t.Fatalf("Put()=%+v err=%v", result, err)
	}
	travelsupport.Count(t, database.Collection("trip_plan_content_links"), bson.M{
		"tripId": "trip_1", "postId": "post_1", "status": model.StatusActive,
	}, 1)
	travelsupport.Count(t, database.Collection("trip_plan_content_link_command_receipts"), bson.M{}, 1)
	travelsupport.Count(t, database.Collection("trip_plan_content_link_outbox"), bson.M{}, 1)
}

func intPointer(value int) *int { return &value }

type contentLinkAuthority struct{}

func (contentLinkAuthority) CanViewTrip(context.Context, string, string) error { return nil }
func (contentLinkAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "persona_owner", nil
}
func (contentLinkAuthority) ValidateAssignment(context.Context, string, int64, int, string) error {
	return nil
}
func (contentLinkAuthority) ValidateVisiblePost(context.Context, string, string, model.Visibility) error {
	return nil
}

type contentLinkIDs struct{}

func (contentLinkIDs) NewTripPlanContentLinkID() (string, error) { return "tcl_post", nil }
func (contentLinkIDs) NewEventID() (string, error)               { return "tev_post", nil }
