// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	mapapplication "quwoquan_service/services/travel-service/internal/travel/trip_map_view/application"
	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	mapports "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/ports"
	momentmodel "quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	planmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	linkmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/application"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/ports"
)

func TestTimelineAndMapShareOneSourceDigestAndExcludeUnconfirmedPersonalMoment(t *testing.T) {
	now := time.Date(2026, 8, 2, 13, 0, 0, 0, time.UTC)
	sources := projectionSources(t, now)
	store := newProjectionStore()
	projector := application.NewProjector(
		store, sources, sources, sources, projectionLinkReader{source: sources},
		func() time.Time { return now },
	)
	event := application.SourceEvent{
		EventID: "tve-1", EventType: "travel.TripMomentChanged", TripID: "trip-1",
	}
	if err := projector.Apply(t.Context(), event); err != nil {
		t.Fatalf("Apply(): %v", err)
	}
	if err := projector.Apply(t.Context(), event); err != nil {
		t.Fatalf("duplicate Apply(): %v", err)
	}
	if store.commitCount != 1 {
		t.Fatalf("commitCount=%d, want 1", store.commitCount)
	}
	timeline := store.timeline
	tripMap := store.tripMap
	if timeline.SourceDigest == "" || timeline.SourceDigest != tripMap.SourceDigest ||
		timeline.CurrentRevisionID != tripMap.CurrentRevisionID {
		t.Fatalf("timeline=%+v map=%+v", timeline, tripMap)
	}
	if len(timeline.SourceMomentIDs) != 2 || len(timeline.SourceContentLinkIDs) != 3 {
		t.Fatalf("timeline source refs=%+v %+v", timeline.SourceMomentIDs, timeline.SourceContentLinkIDs)
	}
	if len(timeline.TripContentLinks) != 1 || timeline.TripContentLinks[0].PostID != "post-trip" ||
		len(timeline.Days) != 2 || len(timeline.Days[0].Items) != 1 ||
		len(timeline.Days[0].Items[0].Moments) != 1 ||
		len(timeline.Days[0].Items[0].ContentLinks) != 1 ||
		len(timeline.Days[1].UnassignedMoments) != 1 ||
		len(timeline.Days[1].UnassignedContentLinks) != 1 {
		t.Fatalf("timeline days=%+v", timeline.Days)
	}
	if len(tripMap.Stops) != 2 || len(tripMap.RouteSegments) != 1 ||
		len(tripMap.MomentMarkers) != 1 || tripMap.Stops[0].ContentLinkIDs[0] != "link-1" {
		t.Fatalf("map=%+v", tripMap)
	}
	timelineReader := application.NewReader(store, sources)
	if view, err := timelineReader.Get(t.Context(), "member", "trip-1"); err != nil ||
		view.SourceDigest != timeline.SourceDigest {
		t.Fatalf("timeline reader view=%+v err=%v", view, err)
	}
	mapReader := mapapplication.NewReader(store, sources)
	if view, err := mapReader.Get(t.Context(), "member", "trip-1"); err != nil ||
		view.SourceDigest != tripMap.SourceDigest {
		t.Fatalf("map reader view=%+v err=%v", view, err)
	}
}

func TestProjectionMissIsRecoverableFailureInsteadOfBusinessEmpty(t *testing.T) {
	store := newProjectionStore()
	authority := &projectionSource{}
	timelineReader := application.NewReader(store, authority)
	if _, err := timelineReader.Get(t.Context(), "member", "trip-missing"); !errors.Is(err, ports.ErrProjectionUnavailable) {
		t.Fatalf("timeline miss err=%v", err)
	}
	mapReader := mapapplication.NewReader(store, authority)
	if _, err := mapReader.Get(t.Context(), "member", "trip-missing"); !errors.Is(err, mapports.ErrProjectionUnavailable) {
		t.Fatalf("map miss err=%v", err)
	}
}

type projectionSource struct {
	plan     planmodel.Plan
	revision revisionmodel.Revision
	moments  []momentmodel.Moment
	links    []linkmodel.Link
}

func projectionSources(t *testing.T, now time.Time) *projectionSource {
	t.Helper()
	start0 := now.Add(time.Hour)
	start1 := now.Add(25 * time.Hour)
	revision, err := revisionmodel.Create(revisionmodel.CreateInput{
		RevisionID: "revision-1", TripID: "trip-1", RevisionNumber: 1,
		ChangeReason: "initial_plan", Severity: revisionmodel.SeverityImportant,
		Items: []revisionmodel.ItemSnapshot{
			{
				ItemID: "west-lake", DayIndex: 0, OrderInDay: 0, Kind: "sight", Title: "西湖",
				StartAt:  &start0,
				PlaceRef: &revisionmodel.PlaceRef{ObjectTypeRef: "entity.Homepage", ObjectID: "place-west-lake"},
			},
			{
				ItemID: "lingyin", DayIndex: 1, OrderInDay: 0, Kind: "sight", Title: "灵隐寺",
				StartAt:  &start1,
				PlaceRef: &revisionmodel.PlaceRef{ObjectTypeRef: "entity.Homepage", ObjectID: "place-lingyin"},
			},
		},
		Changes:            []revisionmodel.Change{{Kind: revisionmodel.ChangeItemAdded, ItemID: "west-lake"}},
		AffectedPersonaIDs: []string{"organizer", "member"}, CreatedByPersonaID: "organizer", CreatedAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	shared, err := momentmodel.Create(momentmodel.CreateInput{
		MomentID: "moment-shared", TripID: "trip-1", RevisionNumber: 1,
		DayIndex: intPtr(0), ItemID: "west-lake", Kind: momentmodel.KindPhoto,
		ContentRef: &momentmodel.ObjectRef{ObjectTypeRef: "content.MediaAsset", ObjectID: "media-1"},
		CapturedAt: now.Add(2 * time.Hour), Visibility: momentmodel.VisibilityTripMembers,
		AssignmentStatus: momentmodel.AssignmentConfirmed, AttributionPersonaID: "member",
		SourceVersion: 1, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	marker, err := momentmodel.Create(momentmodel.CreateInput{
		MomentID: "moment-marker", TripID: "trip-1", RevisionNumber: 1,
		DayIndex: intPtr(1), Kind: momentmodel.KindCheckIn,
		CapturedAt:     now.Add(26 * time.Hour),
		CoarsePlaceRef: &momentmodel.ObjectRef{ObjectTypeRef: "entity.Homepage", ObjectID: "place-lingyin"},
		Visibility:     momentmodel.VisibilityPublic, AssignmentStatus: momentmodel.AssignmentConfirmed,
		AttributionPersonaID: "member", SourceVersion: 1, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	suggested, err := momentmodel.Create(momentmodel.CreateInput{
		MomentID: "moment-private", TripID: "trip-1", RevisionNumber: 1,
		DayIndex: intPtr(0), ItemID: "west-lake", Kind: momentmodel.KindText,
		InlineText: "待确认随拍", CapturedAt: now.Add(3 * time.Hour),
		Visibility: momentmodel.VisibilityPersonal, AssignmentStatus: momentmodel.AssignmentSuggested,
		AttributionPersonaID: "member", SourceVersion: 1, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	link1, err := linkmodel.Create(linkmodel.CreateInput{
		LinkID: "link-1", TripID: "trip-1", PostID: "post-1", RevisionNumber: 1,
		TargetKind: linkmodel.TargetItem, DayIndex: intPtr(0), ItemID: "west-lake",
		Visibility:        linkmodel.VisibilityTripMembers,
		LinkedByPersonaID: "member", SourceVersion: 1, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	link2, err := linkmodel.Create(linkmodel.CreateInput{
		LinkID: "link-2", TripID: "trip-1", PostID: "post-2", RevisionNumber: 1,
		TargetKind: linkmodel.TargetDay, DayIndex: intPtr(1), Visibility: linkmodel.VisibilityPublic,
		LinkedByPersonaID: "member", SourceVersion: 1, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	rootLink, err := linkmodel.Create(linkmodel.CreateInput{
		LinkID: "link-trip", TripID: "trip-1", PostID: "post-trip", RevisionNumber: 1,
		TargetKind: linkmodel.TargetTrip, Visibility: linkmodel.VisibilityPublic,
		LinkedByPersonaID: "member", SourceVersion: 1, Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	return &projectionSource{
		plan: planmodel.Plan{
			TripID: "trip-1", Version: 1, OrganizerPersonaID: "organizer", Title: "杭州两日",
			Status: planmodel.StatusActive, CurrentRevisionID: revision.RevisionID,
			CurrentRevisionNumber: revision.RevisionNumber, CreatedAt: now, UpdatedAt: now,
		},
		revision: revision, moments: []momentmodel.Moment{shared, marker, suggested},
		links: []linkmodel.Link{link1, link2, rootLink},
	}
}

func (source *projectionSource) GetPlan(context.Context, string) (planmodel.Plan, error) {
	return source.plan, nil
}

func (source *projectionSource) Get(context.Context, string, int64) (revisionmodel.Revision, error) {
	return source.revision, nil
}

func (source *projectionSource) ListActive(context.Context, string) ([]momentmodel.Moment, error) {
	return append([]momentmodel.Moment(nil), source.moments...), nil
}

func (source *projectionSource) CanViewTrip(context.Context, string, string) error { return nil }

type projectionLinkReader struct{ source *projectionSource }

func (reader projectionLinkReader) ListActive(context.Context, string) ([]linkmodel.Link, error) {
	return append([]linkmodel.Link(nil), reader.source.links...), nil
}

type projectionStore struct {
	timeline    timelinemodel.View
	tripMap     mapmodel.View
	receipts    map[string]ports.ProjectionReceipt
	commitCount int
}

func newProjectionStore() *projectionStore {
	return &projectionStore{receipts: map[string]ports.ProjectionReceipt{}}
}

func (store *projectionStore) GetTimeline(context.Context, string) (timelinemodel.View, error) {
	if store.timeline.TripID == "" {
		return timelinemodel.View{}, ports.ErrNotFound
	}
	return store.timeline, nil
}

func (store *projectionStore) GetMap(context.Context, string) (mapmodel.View, error) {
	if store.tripMap.TripID == "" {
		return mapmodel.View{}, mapports.ErrNotFound
	}
	return store.tripMap, nil
}

func (store *projectionStore) FindReceipt(
	_ context.Context,
	eventID string,
) (ports.ProjectionReceipt, bool, error) {
	receipt, found := store.receipts[eventID]
	return receipt, found, nil
}

func (store *projectionStore) CommitProjection(_ context.Context, commit ports.ProjectionCommit) error {
	if receipt, found := store.receipts[commit.Receipt.SourceEventID]; found {
		if receipt.TripID != commit.Receipt.TripID || receipt.SourceDigest != commit.Receipt.SourceDigest {
			return ports.ErrReceiptConflict
		}
		return nil
	}
	store.timeline = commit.Timeline
	store.tripMap = commit.Map
	store.receipts[commit.Receipt.SourceEventID] = commit.Receipt
	store.commitCount++
	return nil
}

func intPtr(value int) *int { return &value }
