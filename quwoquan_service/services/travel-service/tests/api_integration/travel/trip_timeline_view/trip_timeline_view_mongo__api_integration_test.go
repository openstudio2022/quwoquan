// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package trip_timeline_view_test

import (
	"context"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripTimelineMongoCommitsTimelineMapAndCheckpointTogether(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_timeline_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	commit := travelsupport.ProjectionCommit()
	if err := store.CommitProjection(t.Context(), commit); err != nil {
		t.Fatal(err)
	}
	actual, err := application.NewReader(store, projectionMembership{}).Get(t.Context(), "persona_member", "trip_1")
	if err != nil || actual.SourceDigest != travelsupport.ProjectionDigest || len(actual.Days) != 1 {
		t.Fatalf("Get()=%+v err=%v", actual, err)
	}
	travelsupport.Count(t, database.Collection("trip_timeline_views"), bson.M{"_id": "trip_1"}, 1)
	travelsupport.Count(t, database.Collection("trip_map_views"), bson.M{"_id": "trip_1"}, 1)
	travelsupport.Count(t, database.Collection("trip_timeline_projection_receipts"), bson.M{"_id": "event_projection"}, 1)
}

type projectionMembership struct{}

func (projectionMembership) CanViewTrip(context.Context, string, string) error { return nil }
