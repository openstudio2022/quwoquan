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

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
)

func TestSuggestedMomentBecomesSharedOnlyAfterExplicitAssignment(t *testing.T) {
	store := newMemoryMomentStore()
	authority := &momentAuthority{}
	service := application.NewService(
		store, authority, authority, authority, authority, &momentIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 11, 0, 0, 0, time.UTC) },
	)
	day := 0
	create := application.CreateCommand{
		ActorPersonaID: "member", IdempotencyKey: "moment-create", TripID: "trip-1",
		RevisionNumber: 1, DayIndex: &day, ItemID: "west-lake",
		Kind:       model.KindPhoto,
		ContentRef: &model.ObjectRef{ObjectTypeRef: "content.MediaAsset", ObjectID: "media-1"},
		CapturedAt: time.Date(2026, 8, 2, 10, 30, 0, 0, time.UTC),
		Visibility: model.VisibilityPersonal, AssignmentStatus: model.AssignmentSuggested,
		SourceVersion: 1,
	}
	created, err := service.Create(t.Context(), create)
	if err != nil {
		t.Fatalf("Create(): %v", err)
	}
	if created.Moment.AssignmentStatus != model.AssignmentSuggested ||
		created.Moment.Visibility != model.VisibilityPersonal {
		t.Fatalf("created=%+v", created)
	}
	replayed, err := service.Create(t.Context(), create)
	if err != nil || !replayed.IdempotentReplay || replayed.Moment.MomentID != created.Moment.MomentID {
		t.Fatalf("replayed=%+v err=%v", replayed, err)
	}
	changed := create
	changed.SourceVersion = 2
	if _, err := service.Create(t.Context(), changed); !errors.Is(err, ports.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict err=%v", err)
	}
	assigned, err := service.Assign(t.Context(), application.AssignCommand{
		ActorPersonaID: "member", IdempotencyKey: "moment-assign", TripID: "trip-1",
		MomentID: created.Moment.MomentID, ExpectedVersion: 1, RevisionNumber: 1,
		DayIndex: 0, ItemID: "west-lake", Visibility: model.VisibilityTripMembers, SourceVersion: 2,
	})
	if err != nil || assigned.Moment.AssignmentStatus != model.AssignmentConfirmed ||
		assigned.Moment.Visibility != model.VisibilityTripMembers || assigned.Moment.Version != 2 {
		t.Fatalf("assigned=%+v err=%v", assigned, err)
	}
	if authority.assignmentCalls != 2 || authority.referenceCalls != 1 {
		t.Fatalf("authority=%+v", authority)
	}
	if moments, err := service.List(t.Context(), "member", "trip-1"); err != nil ||
		len(moments) != 1 || moments[0].ItemID != "west-lake" {
		t.Fatalf("moments=%+v err=%v", moments, err)
	}
	if len(store.moments) != 1 || len(store.receipts) != 2 || len(store.events) != 2 {
		t.Fatalf("moments=%d receipts=%d events=%d", len(store.moments), len(store.receipts), len(store.events))
	}
}

func TestMomentDeleteRequiresOwnerOrOrganizerAndReferenceAuthorityFailsClosed(t *testing.T) {
	store := newMemoryMomentStore()
	authority := &momentAuthority{}
	service := application.NewService(store, authority, authority, authority, authority, &momentIDs{}, time.Now)
	created, err := service.Create(t.Context(), application.CreateCommand{
		ActorPersonaID: "member", IdempotencyKey: "text-create", TripID: "trip-1",
		RevisionNumber: 1, Kind: model.KindText, InlineText: "今天的西湖风很舒服",
		CapturedAt: time.Now(), Visibility: model.VisibilityPersonal,
		AssignmentStatus: model.AssignmentUnassigned, SourceVersion: 0,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.Delete(t.Context(), application.DeleteCommand{
		ActorPersonaID: "another", IdempotencyKey: "delete-denied", TripID: "trip-1",
		MomentID: created.Moment.MomentID, ExpectedVersion: 1, Reason: "无权删除",
	}); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("unauthorized Delete err=%v", err)
	}
	deleted, err := service.Delete(t.Context(), application.DeleteCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "delete-organizer", TripID: "trip-1",
		MomentID: created.Moment.MomentID, ExpectedVersion: 1, Reason: "成员请求移除",
	})
	if err != nil || deleted.Moment.Status != model.StatusDeleted {
		t.Fatalf("deleted=%+v err=%v", deleted, err)
	}
	if moments, err := service.List(t.Context(), "member", "trip-1"); err != nil || len(moments) != 0 {
		t.Fatalf("active moments=%+v err=%v", moments, err)
	}

	failClosed := application.NewReferenceAuthority(nil)
	if err := failClosed.ValidateMomentReferences(
		t.Context(), model.KindPostReference,
		&model.ObjectRef{ObjectTypeRef: "content.Post", ObjectID: "post-1"}, nil, "member",
	); !errors.Is(err, ports.ErrReferenceUnavailable) {
		t.Fatalf("missing Content Reader err=%v", err)
	}
}

type momentAuthority struct {
	assignmentCalls int
	referenceCalls  int
}

func (*momentAuthority) CanViewTrip(context.Context, string, string) error { return nil }

func (*momentAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "organizer", nil
}

func (authority *momentAuthority) ValidateAssignment(
	_ context.Context,
	_ string,
	revisionNumber int64,
	dayIndex int,
	itemID string,
) error {
	authority.assignmentCalls++
	if revisionNumber != 1 || dayIndex != 0 || itemID != "west-lake" {
		return errors.New("assignment not found")
	}
	return nil
}

func (authority *momentAuthority) ValidateMomentReferences(
	_ context.Context,
	_ model.Kind,
	contentRef *model.ObjectRef,
	_ *model.ObjectRef,
	actorPersonaID string,
) error {
	authority.referenceCalls++
	if actorPersonaID == "" || contentRef != nil && contentRef.ObjectID == "" {
		return errors.New("reference unavailable")
	}
	return nil
}

type momentIDs struct {
	value atomic.Int64
}

func (ids *momentIDs) NewTripMomentID() (string, error) {
	return fmt.Sprintf("tmo_%d", ids.value.Add(1)), nil
}

func (ids *momentIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_%d", ids.value.Add(1)), nil
}

type memoryMomentStore struct {
	mu       sync.Mutex
	moments  map[string]model.Moment
	receipts map[string]ports.Receipt
	events   []ports.OutboxEvent
}

func newMemoryMomentStore() *memoryMomentStore {
	return &memoryMomentStore{moments: map[string]model.Moment{}, receipts: map[string]ports.Receipt{}}
}

func (store *memoryMomentStore) Get(_ context.Context, tripID, momentID string) (model.Moment, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	moment, found := store.moments[momentID]
	if !found || moment.TripID != tripID {
		return model.Moment{}, ports.ErrNotFound
	}
	return moment, nil
}

func (store *memoryMomentStore) ListActive(_ context.Context, tripID string) ([]model.Moment, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]model.Moment, 0)
	for _, moment := range store.moments {
		if moment.TripID == tripID && moment.Status == model.StatusActive {
			result = append(result, moment)
		}
	}
	return result, nil
}

func (store *memoryMomentStore) FindReceipt(_ context.Context, key string) (ports.Receipt, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, found := store.receipts[key]
	return receipt, found, nil
}

func (store *memoryMomentStore) Commit(_ context.Context, commit ports.Commit) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return ports.ErrCommitConflict
	}
	current, found := store.moments[commit.Moment.MomentID]
	if commit.ExpectedVersion == 0 {
		if found {
			return ports.ErrCommitConflict
		}
	} else if !found || current.Version != commit.ExpectedVersion {
		return ports.ErrCommitConflict
	}
	store.moments[commit.Moment.MomentID] = commit.Moment
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}
