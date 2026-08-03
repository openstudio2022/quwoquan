// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package trip_share_snapshot_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/application"
	sharemodel "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	shareports "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/infrastructure/persistence"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

const sourceDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func TestTripShareSnapshotMongoCommitsFrozenPrivacyProjection(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_share_snapshot_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	service := application.NewService(store, shareSource{}, shareIDs{}, time.Now)
	result, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "persona_owner", IdempotencyKey: "share-create", TripID: "trip_1",
		SourceRevisionID: "trv_1", SourceDigest: sourceDigest, Scope: sharemodel.ScopeFull,
		MomentIDs: []string{}, Visibility: sharemodel.VisibilityPublic,
	})
	if err != nil || result.Snapshot.SourceDigest != sourceDigest || len(result.Snapshot.RouteStops) != 1 {
		t.Fatalf("Create()=%+v err=%v", result, err)
	}
	travelsupport.Count(t, database.Collection("trip_share_snapshots"), bson.M{"tripId": "trip_1"}, 1)
	travelsupport.Count(t, database.Collection("trip_share_snapshot_command_receipts"), bson.M{}, 1)
	travelsupport.Count(t, database.Collection("trip_share_snapshot_outbox"), bson.M{}, 1)
}

type shareSource struct{}

func (shareSource) ReadShareSource(context.Context, string, string) (shareports.Source, error) {
	return shareports.Source{
		Timeline: timelinemodel.View{
			TripID: "trip_1", CurrentRevisionID: "trv_1", CurrentRevisionNumber: 1,
			SourceDigest:     sourceDigest,
			TripContentLinks: []timelinemodel.ContentLinkSlice{},
			Days: []timelinemodel.DaySlice{{DayIndex: 0, Items: []timelinemodel.ItemSlice{{
				ItemID: "item_west_lake", OrderInDay: 0, Kind: "sight", Title: "西湖",
				PlaceRef: &timelinemodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"},
				Moments:  []timelinemodel.MomentSlice{}, ContentLinks: []timelinemodel.ContentLinkSlice{},
			}}, UnassignedMoments: []timelinemodel.MomentSlice{}, UnassignedContentLinks: []timelinemodel.ContentLinkSlice{}}},
		},
		Map: mapmodel.View{
			TripID: "trip_1", CurrentRevisionID: "trv_1", CurrentRevisionNumber: 1,
			SourceDigest:  sourceDigest,
			Stops:         []mapmodel.Stop{{StopID: "stop_1", Sequence: 0, DayIndex: 0, ItemID: "item_west_lake", Title: "西湖", PlaceRef: mapmodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"}, MomentIDs: []string{}, ContentLinkIDs: []string{}}},
			RouteSegments: []mapmodel.RouteSegment{}, MomentMarkers: []mapmodel.MomentMarker{},
			SourceMomentIDs: []string{}, SourceContentLinkIDs: []string{},
		},
	}, nil
}

type shareIDs struct{}

func (shareIDs) NewTripShareSnapshotID() (string, error) { return "tss_1", nil }
func (shareIDs) NewEventID() (string, error)             { return "tev_share", nil }
