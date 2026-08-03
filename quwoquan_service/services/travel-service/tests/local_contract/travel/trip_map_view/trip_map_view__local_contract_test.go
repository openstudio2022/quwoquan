// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package trip_map_view_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
)

func TestTripMapReaderPreservesTypedRouteAndEnforcesMembership(t *testing.T) {
	view := model.View{
		TripID: "trip_hangzhou", CurrentRevisionID: "trv_2", CurrentRevisionNumber: 2,
		Stops: []model.Stop{
			{StopID: "stop_1", Sequence: 0, DayIndex: 0, ItemID: "item_1", Title: "断桥", PlaceRef: model.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake_broken_bridge"}, MomentIDs: []string{}, ContentLinkIDs: []string{}},
			{StopID: "stop_2", Sequence: 1, DayIndex: 0, ItemID: "item_2", Title: "曲院风荷", PlaceRef: model.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake_quyuan"}, MomentIDs: []string{"moment_1"}, ContentLinkIDs: []string{"link_1"}},
		},
		RouteSegments: []model.RouteSegment{{SegmentID: "segment_1", Sequence: 0, FromStopID: "stop_1", ToStopID: "stop_2"}},
		MomentMarkers: []model.MomentMarker{}, SourceMomentIDs: []string{"moment_1"}, SourceContentLinkIDs: []string{"link_1"},
		SourceDigest:  "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		SourceEventID: "event_2", ProjectedAt: time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC),
	}
	reader := application.NewReader(mapStoreStub{view: view}, membershipStub{})
	actual, err := reader.Get(t.Context(), "persona_member", "trip_hangzhou")
	if err != nil || actual.SourceDigest != view.SourceDigest || len(actual.RouteSegments) != 1 {
		t.Fatalf("Get()=%+v err=%v", actual, err)
	}
	if _, err := reader.Get(t.Context(), "persona_denied", "trip_hangzhou"); !errors.Is(err, errDenied) {
		t.Fatalf("denied reader error=%v", err)
	}
}

type mapStoreStub struct{ view model.View }

func (stub mapStoreStub) GetMap(context.Context, string) (model.View, error) { return stub.view, nil }

var errDenied = errors.New("trip membership required")

type membershipStub struct{}

func (membershipStub) CanViewTrip(_ context.Context, personaID, _ string) error {
	if personaID == "persona_denied" {
		return errDenied
	}
	return nil
}
