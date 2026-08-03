// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/ports"
)

func TestSurfaceReaderReturnsMultipleTripsWithoutGuessingMutationTarget(t *testing.T) {
	store := newMemoryPlacementStore()
	authority := &placementAuthority{organizerID: "organizer"}
	service := application.NewService(
		store, authority, authority, authority, &placementIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC) },
	)
	for index, tripID := range []string{"trip-west-lake", "trip-lingyin"} {
		created, err := service.Put(t.Context(), application.PutCommand{
			ActorPersonaID: "organizer", IdempotencyKey: fmt.Sprintf("put-%d", index),
			TripID: tripID, SurfaceKind: model.SurfaceConversation, SurfaceID: "conversation-shared",
			SourceVersion: 12, ExpectedVersion: 0,
		})
		if err != nil || created.Placement.TripID != tripID || created.Placement.Status != model.StatusActive {
			t.Fatalf("trip=%s created=%+v err=%v", tripID, created, err)
		}
	}
	candidates, err := service.ListBySurface(
		t.Context(), "member", model.SurfaceConversation, "conversation-shared",
	)
	if err != nil || len(candidates) != 2 {
		t.Fatalf("candidates=%+v err=%v", candidates, err)
	}
	if len(store.receipts) != 2 || len(store.events) != 2 {
		t.Fatalf("receipts=%d events=%d", len(store.receipts), len(store.events))
	}
	// A shared-surface query only returns candidates. It never selects a Trip or
	// writes a revision on behalf of Assistant routing.
	for _, candidate := range candidates {
		if candidate.Version != 1 || candidate.Status != model.StatusActive {
			t.Fatalf("candidate mutated during disambiguation: %+v", candidate)
		}
	}
}

func TestPlacementRemovalBlocksStaleReactivationAndUsesAtomicReceipt(t *testing.T) {
	store := newMemoryPlacementStore()
	authority := &placementAuthority{organizerID: "organizer"}
	service := application.NewService(store, authority, authority, authority, &placementIDs{}, time.Now)
	put := application.PutCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "placement-put", TripID: "trip-1",
		SurfaceKind: model.SurfaceCircle, SurfaceID: "circle-1", SourceVersion: 20, ExpectedVersion: 0,
	}
	created, err := service.Put(t.Context(), put)
	if err != nil {
		t.Fatal(err)
	}
	replayed, err := service.Put(t.Context(), put)
	if err != nil || !replayed.IdempotentReplay || replayed.Placement.PlacementID != created.Placement.PlacementID {
		t.Fatalf("replayed=%+v err=%v", replayed, err)
	}
	changed := put
	changed.SourceVersion = 21
	if _, err := service.Put(t.Context(), changed); !errors.Is(err, ports.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict err=%v", err)
	}
	removed, err := service.Remove(t.Context(), application.RemoveCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "placement-remove", TripID: "trip-1",
		SurfaceKind: model.SurfaceCircle, SurfaceID: "circle-1", SourceVersion: 21, ExpectedVersion: 1,
	})
	if err != nil || removed.Placement.Status != model.StatusRemoved || removed.Placement.Version != 2 {
		t.Fatalf("removed=%+v err=%v", removed, err)
	}
	if active, err := service.ListBySurface(t.Context(), "member", model.SurfaceCircle, "circle-1"); err != nil || len(active) != 0 {
		t.Fatalf("active=%+v err=%v", active, err)
	}
	if _, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "placement-stale-reactivate", TripID: "trip-1",
		SurfaceKind: model.SurfaceCircle, SurfaceID: "circle-1", SourceVersion: 21, ExpectedVersion: 2,
	}); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("stale reactivation err=%v", err)
	}
	restored, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "placement-reactivate", TripID: "trip-1",
		SurfaceKind: model.SurfaceCircle, SurfaceID: "circle-1", SourceVersion: 22, ExpectedVersion: 2,
	})
	if err != nil || restored.Placement.Status != model.StatusActive || restored.Placement.Version != 3 {
		t.Fatalf("restored=%+v err=%v", restored, err)
	}
	if len(store.placements) != 1 || len(store.receipts) != 3 || len(store.events) != 3 {
		t.Fatalf(
			"placements=%d receipts=%d events=%d",
			len(store.placements), len(store.receipts), len(store.events),
		)
	}
}

type placementAuthority struct {
	organizerID string
	adminErr    error
	memberErr   error
	viewErr     error
}

func (authority *placementAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return authority.organizerID, nil
}

func (authority *placementAuthority) CanViewTrip(context.Context, string, string) error {
	return authority.viewErr
}

func (authority *placementAuthority) RequireAdmin(
	context.Context,
	model.SurfaceKind,
	string,
	string,
	int64,
) error {
	return authority.adminErr
}

func (authority *placementAuthority) RequireMember(
	context.Context,
	model.SurfaceKind,
	string,
	string,
) error {
	return authority.memberErr
}

type placementIDs struct {
	value atomic.Int64
}

func (ids *placementIDs) NewTripPlanPlacementID() (string, error) {
	return fmt.Sprintf("tpl_%d", ids.value.Add(1)), nil
}

func (ids *placementIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_%d", ids.value.Add(1)), nil
}

type memoryPlacementStore struct {
	mu         sync.Mutex
	placements map[string]model.Placement
	receipts   map[string]ports.Receipt
	events     []ports.OutboxEvent
}

func newMemoryPlacementStore() *memoryPlacementStore {
	return &memoryPlacementStore{
		placements: map[string]model.Placement{},
		receipts:   map[string]ports.Receipt{},
	}
}

func placementKey(tripID string, kind model.SurfaceKind, surfaceID string) string {
	return tripID + ":" + string(kind) + ":" + surfaceID
}

func (store *memoryPlacementStore) Get(
	_ context.Context,
	tripID string,
	kind model.SurfaceKind,
	surfaceID string,
) (model.Placement, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	placement, found := store.placements[placementKey(tripID, kind, surfaceID)]
	if !found {
		return model.Placement{}, ports.ErrNotFound
	}
	return placement, nil
}

func (store *memoryPlacementStore) ListByTrip(
	_ context.Context,
	tripID string,
) ([]model.Placement, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]model.Placement, 0)
	for _, placement := range store.placements {
		if placement.TripID == tripID {
			result = append(result, placement)
		}
	}
	return result, nil
}

func (store *memoryPlacementStore) ListActiveBySurface(
	_ context.Context,
	kind model.SurfaceKind,
	surfaceID string,
) ([]model.Placement, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]model.Placement, 0)
	for _, placement := range store.placements {
		if placement.SurfaceKind == kind && placement.SurfaceID == surfaceID && placement.Status == model.StatusActive {
			result = append(result, placement)
		}
	}
	return result, nil
}

func (store *memoryPlacementStore) FindReceipt(
	_ context.Context,
	key string,
) (ports.Receipt, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, found := store.receipts[key]
	return receipt, found, nil
}

func (store *memoryPlacementStore) Commit(_ context.Context, commit ports.Commit) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return ports.ErrCommitConflict
	}
	key := placementKey(commit.Placement.TripID, commit.Placement.SurfaceKind, commit.Placement.SurfaceID)
	current, found := store.placements[key]
	if commit.ExpectedVersion == 0 {
		if found {
			return ports.ErrCommitConflict
		}
	} else if !found || current.Version != commit.ExpectedVersion {
		return ports.ErrCommitConflict
	}
	store.placements[key] = commit.Placement
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}
