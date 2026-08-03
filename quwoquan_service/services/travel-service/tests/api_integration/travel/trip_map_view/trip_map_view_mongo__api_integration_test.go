// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package trip_map_view_test

import (
	"context"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/application"
	mappersistence "quwoquan_service/services/travel-service/internal/travel/trip_map_view/infrastructure/persistence"
	timelinepersistence "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripMapMongoReadsTheSameFrozenProjectionDigest(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_map_api_integration")
	projectionStore := timelinepersistence.NewMongoStore(database)
	if err := projectionStore.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	if err := projectionStore.CommitProjection(t.Context(), travelsupport.ProjectionCommit()); err != nil {
		t.Fatal(err)
	}
	mapStore := mappersistence.NewMongoStore(database)
	if err := mapStore.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	actual, err := application.NewReader(mapStore, mapMembership{}).Get(t.Context(), "persona_member", "trip_1")
	if err != nil || actual.SourceDigest != travelsupport.ProjectionDigest || len(actual.Stops) != 1 {
		t.Fatalf("Get()=%+v err=%v", actual, err)
	}
}

type mapMembership struct{}

func (mapMembership) CanViewTrip(context.Context, string, string) error { return nil }
