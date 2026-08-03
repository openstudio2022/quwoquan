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

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/ports"
)

func TestTripMembershipUsesOrganizerAuthorityCASReceiptAndOutboxAtomically(t *testing.T) {
	store := newMemoryMembershipStore()
	authority := &tripAuthority{organizerID: "persona-organizer"}
	service := application.NewService(
		store,
		authority,
		application.NewSourceAuthority(nil),
		&membershipIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC) },
	)
	put := application.PutCommand{
		ActorPersonaID:  "persona-organizer",
		IdempotencyKey:  "membership-put-1",
		TripID:          "trip-1",
		PersonaID:       "persona-member",
		ExpectedVersion: 0,
		Role:            model.RoleParticipant,
		SourceKind:      model.SourceTripInvitation,
		SourceVersion:   0,
	}
	created, err := service.Put(t.Context(), put)
	if err != nil {
		t.Fatalf("Put(): %v", err)
	}
	if created.Membership.Version != 1 || created.Membership.State != model.StateActive {
		t.Fatalf("created=%+v", created)
	}
	assertMembershipAtomicCounts(t, store, 1, 1, 1)

	replayed, err := service.Put(t.Context(), put)
	if err != nil || !replayed.IdempotentReplay || replayed.Membership.MembershipID != created.Membership.MembershipID {
		t.Fatalf("replayed=%+v err=%v", replayed, err)
	}
	assertMembershipAtomicCounts(t, store, 1, 1, 1)

	changed := put
	changed.Role = model.RoleLeader
	if _, err := service.Put(t.Context(), changed); !errors.Is(err, ports.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict err=%v", err)
	}

	unauthorized := put
	unauthorized.IdempotencyKey = "membership-put-unauthorized"
	unauthorized.ActorPersonaID = "persona-member"
	unauthorized.PersonaID = "persona-another"
	if _, err := service.Put(t.Context(), unauthorized); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("unauthorized Put err=%v", err)
	}

	departed, err := service.Depart(t.Context(), application.DepartCommand{
		ActorPersonaID:  "persona-member",
		IdempotencyKey:  "membership-depart-1",
		TripID:          "trip-1",
		PersonaID:       "persona-member",
		ExpectedVersion: 1,
		Reason:          "行程结束",
	})
	if err != nil || departed.Membership.State != model.StateLeft || departed.Membership.Version != 2 {
		t.Fatalf("departed=%+v err=%v", departed, err)
	}
	assertMembershipAtomicCounts(t, store, 1, 2, 2)
	if _, err := service.List(t.Context(), "persona-member", "trip-1"); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("departed member List err=%v", err)
	}
	if memberships, err := service.List(t.Context(), "persona-organizer", "trip-1"); err != nil || len(memberships) != 1 {
		t.Fatalf("organizer memberships=%+v err=%v", memberships, err)
	}
}

func TestTripMembershipExternalSourceRequiresTypedResolverAndMonotonicVersion(t *testing.T) {
	store := newMemoryMembershipStore()
	source := &recordingSourceResolver{}
	service := application.NewService(
		store,
		&tripAuthority{organizerID: "organizer"},
		application.NewSourceAuthority(map[model.SourceKind]application.MembershipSourceResolver{
			model.SourceConversation: source,
		}),
		&membershipIDs{},
		time.Now,
	)
	ref := &model.SourceRef{ObjectTypeRef: "chat.Conversation", ObjectID: "conversation-1"}
	created, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "put-conversation", TripID: "trip-1",
		PersonaID: "member", ExpectedVersion: 0, Role: model.RoleParticipant,
		SourceKind: model.SourceConversation, SourceObjectRef: ref, SourceVersion: 8,
	})
	if err != nil || source.calls != 1 || source.version != 8 {
		t.Fatalf("created=%+v resolver=%+v err=%v", created, source, err)
	}
	if _, err := service.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "put-stale", TripID: "trip-1",
		PersonaID: "member", ExpectedVersion: 1, Role: model.RoleLeader,
		SourceKind: model.SourceConversation, SourceObjectRef: ref, SourceVersion: 7,
	}); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("stale source version err=%v", err)
	}

	unavailable := application.NewService(
		newMemoryMembershipStore(),
		&tripAuthority{organizerID: "organizer"},
		application.NewSourceAuthority(nil),
		&membershipIDs{},
		time.Now,
	)
	if _, err := unavailable.Put(t.Context(), application.PutCommand{
		ActorPersonaID: "organizer", IdempotencyKey: "put-unavailable", TripID: "trip-2",
		PersonaID: "member", ExpectedVersion: 0, Role: model.RoleParticipant,
		SourceKind: model.SourceConversation, SourceObjectRef: ref, SourceVersion: 1,
	}); !errors.Is(err, ports.ErrSourceUnavailable) {
		t.Fatalf("missing source resolver err=%v", err)
	}
}

type tripAuthority struct {
	organizerID string
	err         error
}

func (authority *tripAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return authority.organizerID, authority.err
}

type recordingSourceResolver struct {
	calls   int
	ref     model.SourceRef
	version int64
}

func (resolver *recordingSourceResolver) ValidateMembershipSource(
	_ context.Context,
	ref model.SourceRef,
	version int64,
	personaID string,
) error {
	resolver.calls++
	resolver.ref = ref
	resolver.version = version
	if personaID != "member" {
		return model.ErrInvalidArgument
	}
	return nil
}

type membershipIDs struct {
	value atomic.Int64
}

func (ids *membershipIDs) NewTripMembershipID() (string, error) {
	return fmt.Sprintf("tpm_%d", ids.value.Add(1)), nil
}

func (ids *membershipIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_%d", ids.value.Add(1)), nil
}

type memoryMembershipStore struct {
	mu          sync.Mutex
	memberships map[string]model.Membership
	receipts    map[string]ports.Receipt
	events      []ports.OutboxEvent
}

func newMemoryMembershipStore() *memoryMembershipStore {
	return &memoryMembershipStore{
		memberships: map[string]model.Membership{},
		receipts:    map[string]ports.Receipt{},
	}
}

func membershipKey(tripID, personaID string) string {
	return tripID + ":" + personaID
}

func (store *memoryMembershipStore) Get(
	_ context.Context,
	tripID string,
	personaID string,
) (model.Membership, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	membership, found := store.memberships[membershipKey(tripID, personaID)]
	if !found {
		return model.Membership{}, ports.ErrNotFound
	}
	return membership, nil
}

func (store *memoryMembershipStore) List(_ context.Context, tripID string) ([]model.Membership, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]model.Membership, 0)
	for _, membership := range store.memberships {
		if membership.TripID == tripID {
			result = append(result, membership)
		}
	}
	return result, nil
}

func (store *memoryMembershipStore) FindReceipt(
	_ context.Context,
	key string,
) (ports.Receipt, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	receipt, found := store.receipts[key]
	return receipt, found, nil
}

func (store *memoryMembershipStore) Commit(_ context.Context, commit ports.Commit) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return ports.ErrCommitConflict
	}
	key := membershipKey(commit.Membership.TripID, commit.Membership.PersonaID)
	current, found := store.memberships[key]
	if commit.ExpectedVersion == 0 {
		if found {
			return ports.ErrCommitConflict
		}
	} else if !found || current.Version != commit.ExpectedVersion {
		return ports.ErrCommitConflict
	}
	store.memberships[key] = commit.Membership
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}

func assertMembershipAtomicCounts(
	t *testing.T,
	store *memoryMembershipStore,
	memberships int,
	receipts int,
	events int,
) {
	t.Helper()
	store.mu.Lock()
	defer store.mu.Unlock()
	if len(store.memberships) != memberships || len(store.receipts) != receipts || len(store.events) != events {
		t.Fatalf(
			"counts memberships=%d receipts=%d events=%d",
			len(store.memberships), len(store.receipts), len(store.events),
		)
	}
}
