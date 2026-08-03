// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
)

func TestPostLinkIsAdoptedMovedAndRemovedWithoutCopyingPost(t *testing.T) {
	store := newMemoryLinkStore()
	authority := &linkAuthority{}
	service := application.NewService(
		store, authority, authority, authority, authority, &linkIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC) },
	)
	put := application.PutCommand{
		ActorPersonaID: "member", IdempotencyKey: "link-put", TripID: "trip-1", PostID: "post-1",
		ExpectedVersion: 0, RevisionNumber: 1, TargetKind: model.TargetItem,
		DayIndex: intPointer(0), ItemID: "west-lake",
		Visibility: model.VisibilityTripMembers, SourceVersion: 1,
	}
	created, err := service.Put(t.Context(), put)
	if err != nil {
		t.Fatalf("Put(): %v", err)
	}
	if created.Link.PostID != "post-1" || created.Link.ItemID != "west-lake" ||
		created.Link.Status != model.StatusActive || created.Link.Version != 1 {
		t.Fatalf("created=%+v", created)
	}
	replayed, err := service.Put(t.Context(), put)
	if err != nil || !replayed.IdempotentReplay || replayed.Link.LinkID != created.Link.LinkID {
		t.Fatalf("replayed=%+v err=%v", replayed, err)
	}
	changed := put
	changed.SourceVersion = 2
	if _, err := service.Put(t.Context(), changed); !errors.Is(err, ports.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict err=%v", err)
	}
	moved, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "member", IdempotencyKey: "link-move", TripID: "trip-1", PostID: "post-1",
		ExpectedVersion: 1, RevisionNumber: 2, TargetKind: model.TargetItem,
		DayIndex: intPointer(1), ItemID: "lingyin",
		Visibility: model.VisibilityPublic, SourceVersion: 2,
	})
	if err != nil || moved.Link.Version != 2 || moved.Link.RevisionNumber != 2 ||
		moved.Link.DayIndex == nil || *moved.Link.DayIndex != 1 || moved.Link.ItemID != "lingyin" ||
		moved.Link.Visibility != model.VisibilityPublic {
		t.Fatalf("moved=%+v err=%v", moved, err)
	}
	if authority.assignmentCalls != 2 || authority.postCalls != 2 || !authority.lastRequirePublic {
		t.Fatalf("authority=%+v", authority)
	}
	if links, err := service.List(t.Context(), "member", "trip-1"); err != nil ||
		len(links) != 1 || links[0].PostID != "post-1" {
		t.Fatalf("links=%+v err=%v", links, err)
	}
	removed, err := service.Remove(t.Context(), application.RemoveCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "link-remove", TripID: "trip-1", PostID: "post-1",
		ExpectedVersion: 2, Reason: "行程内容已更新",
	})
	if err != nil || removed.Link.Status != model.StatusRemoved || removed.Link.Version != 3 {
		t.Fatalf("removed=%+v err=%v", removed, err)
	}
	if links, err := service.List(t.Context(), "member", "trip-1"); err != nil || len(links) != 0 {
		t.Fatalf("active links=%+v err=%v", links, err)
	}
	if len(store.links) != 1 || len(store.receipts) != 3 || len(store.events) != 3 {
		t.Fatalf("links=%d receipts=%d events=%d", len(store.links), len(store.receipts), len(store.events))
	}
}

func TestPostAuthorityAndReactivationFailClosed(t *testing.T) {
	failClosed := application.NewPostAuthority(nil)
	if err := failClosed.ValidateVisiblePost(
		t.Context(), "member", "post-1", model.VisibilityTripMembers,
	); !errors.Is(err, ports.ErrPostUnavailable) {
		t.Fatalf("missing Content Reader err=%v", err)
	}

	store := newMemoryLinkStore()
	authority := &linkAuthority{}
	service := application.NewService(store, authority, authority, authority, authority, &linkIDs{}, time.Now)
	created, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "member", IdempotencyKey: "put", TripID: "trip-1", PostID: "post-1",
		RevisionNumber: 1, TargetKind: model.TargetTrip,
		Visibility: model.VisibilityTripMembers, SourceVersion: 5,
	})
	if err != nil {
		t.Fatal(err)
	}
	removed, err := service.Remove(t.Context(), application.RemoveCommand{
		ActorPersonaID: "member", IdempotencyKey: "remove", TripID: "trip-1", PostID: "post-1",
		ExpectedVersion: created.Link.Version, Reason: "暂时移除",
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "member", IdempotencyKey: "stale-reactivation", TripID: "trip-1", PostID: "post-1",
		ExpectedVersion: removed.Link.Version, RevisionNumber: 1, TargetKind: model.TargetTrip,
		Visibility: model.VisibilityTripMembers, SourceVersion: 5,
	}); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("stale reactivation err=%v", err)
	}
	reactivated, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "member", IdempotencyKey: "fresh-reactivation", TripID: "trip-1", PostID: "post-1",
		ExpectedVersion: removed.Link.Version, RevisionNumber: 1, TargetKind: model.TargetTrip,
		Visibility: model.VisibilityTripMembers, SourceVersion: 6,
	})
	if err != nil || reactivated.Link.Status != model.StatusActive || reactivated.Link.Version != 3 {
		t.Fatalf("reactivated=%+v err=%v", reactivated, err)
	}
}

type linkAuthority struct {
	assignmentCalls   int
	postCalls         int
	lastRequirePublic bool
}

func (*linkAuthority) CanViewTrip(context.Context, string, string) error { return nil }

func (*linkAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "organizer", nil
}

func (authority *linkAuthority) ValidateAssignment(
	_ context.Context,
	_ string,
	revisionNumber int64,
	dayIndex int,
	itemID string,
) error {
	authority.assignmentCalls++
	if revisionNumber <= 0 || dayIndex < 0 || itemID == "unknown" {
		return errors.New("assignment not found")
	}
	return nil
}

func (authority *linkAuthority) ValidateVisiblePost(
	_ context.Context,
	actorPersonaID string,
	postID string,
	visibility model.Visibility,
) error {
	authority.postCalls++
	authority.lastRequirePublic = visibility == model.VisibilityPublic
	if actorPersonaID == "" || postID == "" {
		return ports.ErrPostUnavailable
	}
	return nil
}

type linkIDs struct {
	value atomic.Int64
}

func (ids *linkIDs) NewTripPlanContentLinkID() (string, error) {
	return fmt.Sprintf("tcl_%d", ids.value.Add(1)), nil
}

func (ids *linkIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_%d", ids.value.Add(1)), nil
}

func intPointer(value int) *int { return &value }

type memoryLinkStore struct {
	mu       sync.Mutex
	links    map[string]model.Link
	receipts map[string]ports.Receipt
	events   []ports.OutboxEvent
}

func newMemoryLinkStore() *memoryLinkStore {
	return &memoryLinkStore{links: map[string]model.Link{}, receipts: map[string]ports.Receipt{}}
}

func linkKey(tripID, postID string) string { return tripID + "\x00" + postID }

func (store *memoryLinkStore) Get(_ context.Context, tripID, postID string) (model.Link, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	link, found := store.links[linkKey(tripID, postID)]
	if !found {
		return model.Link{}, ports.ErrNotFound
	}
	return link, nil
}

func (store *memoryLinkStore) ListActive(_ context.Context, tripID string) ([]model.Link, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]model.Link, 0)
	for _, link := range store.links {
		if link.TripID == tripID && link.Status == model.StatusActive {
			result = append(result, link)
		}
	}
	return result, nil
}

func (store *memoryLinkStore) FindReceipt(_ context.Context, key string) (ports.Receipt, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, found := store.receipts[key]
	return receipt, found, nil
}

func (store *memoryLinkStore) Commit(_ context.Context, commit ports.Commit) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return ports.ErrCommitConflict
	}
	key := linkKey(commit.Link.TripID, commit.Link.PostID)
	current, found := store.links[key]
	if commit.ExpectedVersion == 0 {
		if found {
			return ports.ErrCommitConflict
		}
	} else if !found || current.Version != commit.ExpectedVersion {
		return ports.ErrCommitConflict
	}
	store.links[key] = commit.Link
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}
