// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package trip_share_snapshot_test

import (
	"context"
	"errors"
	"testing"
	"time"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	momentmodel "quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	linkmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	shareapplication "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/application"
	sharemodel "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	shareports "quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/ports"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
)

func TestPublicShareSnapshotFreezesSourceAndRemovesPrivateTravelFacts(t *testing.T) {
	store := &memoryStore{snapshots: map[string]sharemodel.Snapshot{}, receipts: map[string]shareports.Receipt{}}
	source := sourceStub{source: canonicalSource()}
	service := shareapplication.NewService(
		store, source, idsStub{},
		func() time.Time { return time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC) },
	)
	command := shareapplication.CreateCommand{
		ActorPersonaID: "persona_owner", IdempotencyKey: "share-command-1",
		TripID: "trip_hangzhou", SourceRevisionID: "revision_2",
		SourceDigest: digest, Scope: sharemodel.ScopeFull,
		MomentIDs: []string{}, Visibility: sharemodel.VisibilityPublic,
	}
	result, err := service.Create(t.Context(), command)
	if err != nil {
		t.Fatal(err)
	}
	snapshot := result.Snapshot
	if snapshot.SourceRevisionNumber != 2 || snapshot.SourceDigest != digest ||
		snapshot.PrivacyPolicyDigest != sharemodel.PrivacyPolicyDigestV1 || len(store.events) != 1 {
		t.Fatalf("snapshot source/event mismatch: %+v events=%+v", snapshot, store.events)
	}
	if len(snapshot.Items) != 2 || snapshot.Items[0].Kind != "stay" ||
		snapshot.Items[0].Title != "" || snapshot.Items[0].PlaceRef != nil {
		t.Fatalf("public stay was not redacted: %+v", snapshot.Items)
	}
	if len(snapshot.Moments) != 1 || snapshot.Moments[0].MomentID != "moment_public" ||
		len(snapshot.ContentLinks) != 1 || snapshot.ContentLinks[0].PostID != "post_public" ||
		len(snapshot.RouteStops) != 1 || snapshot.RouteStops[0].ItemID != "item_sight" {
		t.Fatalf("public privacy projection mismatch: %+v", snapshot)
	}
	replay, err := service.Create(t.Context(), command)
	if err != nil || !replay.IdempotentReplay || len(store.events) != 1 {
		t.Fatalf("idempotent replay=%+v events=%d err=%v", replay, len(store.events), err)
	}
	command.Visibility = sharemodel.VisibilityTripMembers
	if _, err := service.Create(t.Context(), command); !errors.Is(err, shareports.ErrIdempotencyConflict) {
		t.Fatalf("changed duplicate command error=%v", err)
	}
}

func TestShareSnapshotRejectsStaleRevisionAndEmptyPublicMomentCollection(t *testing.T) {
	store := &memoryStore{snapshots: map[string]sharemodel.Snapshot{}, receipts: map[string]shareports.Receipt{}}
	service := shareapplication.NewService(store, sourceStub{source: canonicalSource()}, idsStub{}, time.Now)
	base := shareapplication.CreateCommand{
		ActorPersonaID: "persona_owner", IdempotencyKey: "share-stale",
		TripID: "trip_hangzhou", SourceRevisionID: "revision_old", SourceDigest: digest,
		Scope: sharemodel.ScopeFull, MomentIDs: []string{}, Visibility: sharemodel.VisibilityPublic,
	}
	if _, err := service.Create(t.Context(), base); !errors.Is(err, sharemodel.ErrSourceConflict) {
		t.Fatalf("stale revision error=%v", err)
	}
	base.IdempotencyKey = "share-private-moment"
	base.SourceRevisionID = "revision_2"
	base.Scope = sharemodel.ScopeMomentCollection
	base.MomentIDs = []string{"moment_members"}
	if _, err := service.Create(t.Context(), base); !errors.Is(err, sharemodel.ErrInvalidArgument) {
		t.Fatalf("empty public moment collection error=%v", err)
	}
}

const digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func canonicalSource() shareports.Source {
	return shareports.Source{
		Timeline: timelinemodel.View{
			TripID: "trip_hangzhou", CurrentRevisionID: "revision_2",
			CurrentRevisionNumber: 2, SourceDigest: digest,
			TripContentLinks: []timelinemodel.ContentLinkSlice{},
			Days: []timelinemodel.DaySlice{{
				DayIndex: 0, UnassignedMoments: []timelinemodel.MomentSlice{},
				UnassignedContentLinks: []timelinemodel.ContentLinkSlice{},
				Items: []timelinemodel.ItemSlice{
					{
						ItemID: "item_stay", OrderInDay: 0, Kind: "stay", Title: "西湖边酒店 1208 房",
						PlaceRef: &timelinemodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "private_hotel"},
						Moments: []timelinemodel.MomentSlice{{
							MomentID: "moment_members", Kind: momentmodel.KindPhoto,
							Visibility: momentmodel.VisibilityTripMembers,
						}},
						ContentLinks: []timelinemodel.ContentLinkSlice{{
							LinkID: "link_members", PostID: "post_members", Visibility: linkmodel.VisibilityTripMembers,
						}},
					},
					{
						ItemID: "item_sight", OrderInDay: 1, Kind: "sight", Title: "西湖",
						PlaceRef: &timelinemodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"},
						Moments: []timelinemodel.MomentSlice{{
							MomentID: "moment_public", Kind: momentmodel.KindPhoto,
							Visibility: momentmodel.VisibilityPublic,
						}},
						ContentLinks: []timelinemodel.ContentLinkSlice{{
							LinkID: "link_public", PostID: "post_public", Visibility: linkmodel.VisibilityPublic,
						}},
					},
				},
			}},
		},
		Map: mapmodel.View{
			TripID: "trip_hangzhou", CurrentRevisionID: "revision_2",
			CurrentRevisionNumber: 2, SourceDigest: digest,
			Stops: []mapmodel.Stop{
				{StopID: "stop_stay", Sequence: 0, DayIndex: 0, ItemID: "item_stay", Title: "酒店", PlaceRef: mapmodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "private_hotel"}},
				{StopID: "stop_sight", Sequence: 1, DayIndex: 0, ItemID: "item_sight", Title: "西湖", PlaceRef: mapmodel.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"}},
			},
		},
	}
}

type sourceStub struct{ source shareports.Source }

func (stub sourceStub) ReadShareSource(context.Context, string, string) (shareports.Source, error) {
	return stub.source, nil
}

type idsStub struct{}

func (idsStub) NewTripShareSnapshotID() (string, error) { return "tss_snapshot", nil }
func (idsStub) NewEventID() (string, error)             { return "tev_snapshot", nil }

type memoryStore struct {
	snapshots map[string]sharemodel.Snapshot
	receipts  map[string]shareports.Receipt
	events    []shareports.OutboxEvent
}

func (store *memoryStore) Get(_ context.Context, id string) (sharemodel.Snapshot, error) {
	value, found := store.snapshots[id]
	if !found {
		return sharemodel.Snapshot{}, shareports.ErrNotFound
	}
	return value, nil
}

func (store *memoryStore) FindReceipt(_ context.Context, key string) (shareports.Receipt, bool, error) {
	value, found := store.receipts[key]
	return value, found, nil
}

func (store *memoryStore) Commit(_ context.Context, commit shareports.Commit) error {
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return shareports.ErrIdempotencyConflict
		}
		return nil
	}
	store.snapshots[commit.Snapshot.SnapshotID] = commit.Snapshot
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}
