package circlepostplacement

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	placementmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/model"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
	generated "quwoquan_service/services/circle-service/internal/generated"
)

func TestPlaceRequiresTrustedOwnerOrModeratorAndReplaysReceipt(t *testing.T) {
	store := newContractStore()
	readers := contractReaders{
		circle: placementports.CirclePolicySlice{CircleID: "circle-1", OwnerPersonaID: "persona-moderator", State: "active"},
		group:  placementports.GroupPolicySlice{GroupID: "group-1", CircleID: "circle-1", State: "active"},
		post:   placementports.PostOwnerSlice{PostID: "post-1", OwnerPersonaID: "persona-owner", State: "published"},
	}
	facade := NewCommandFacade(store, readers.policyReaders())
	facade.now = func() time.Time { return time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC) }
	facade.newID = func() (string, error) { return "placement-1", nil }

	ctx := placementContext("persona-owner", "place-1")
	first, err := facade.Place(ctx, PlaceCommand{CircleID: "circle-1", PostID: "post-1", GroupID: "group-1"})
	if err != nil || first.IdempotentReplay || first.Version != 1 || first.State != "active" {
		t.Fatalf("first place drift: result=%+v err=%v", first, err)
	}
	replayed, err := facade.Place(ctx, PlaceCommand{CircleID: "circle-1", PostID: "post-1", GroupID: "group-1"})
	if err != nil || !replayed.IdempotentReplay || replayed.PlacementID != first.PlacementID {
		t.Fatalf("replay drift: result=%+v err=%v", replayed, err)
	}

	_, err = facade.Place(placementContext("persona-outsider", "place-2"), PlaceCommand{
		CircleID: "circle-1", PostID: "post-1", GroupID: "group-1",
	})
	if !hasRuntimeCode(err, generated.ErrPermissionDenied.Error()) {
		t.Fatalf("outsider must be denied, got %v", err)
	}
}

func TestPresentationRequiresModeratorAndExpectedVersion(t *testing.T) {
	store := newContractStore()
	store.placement = &placementmodel.CirclePostPlacement{
		ID: "placement-1", Version: 1, PostID: "post-1", OwnerPersonaID: "persona-owner",
		CircleID: "circle-1", State: placementmodel.CirclePostPlacementStateActive,
		CreatedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC(), LastActiveAt: time.Now().UTC(),
	}
	readers := contractReaders{
		circle: placementports.CirclePolicySlice{CircleID: "circle-1", OwnerPersonaID: "persona-moderator", State: "active"},
	}
	facade := NewCommandFacade(store, readers.policyReaders())
	facade.now = func() time.Time { return time.Date(2026, 7, 14, 9, 0, 0, 0, time.UTC) }

	_, err := facade.SetPinned(placementContext("persona-owner", "pin-owner"), PresentationCommand{
		CircleID: "circle-1", PlacementID: "placement-1", ExpectedVersion: 1, Enabled: true,
	})
	if !hasRuntimeCode(err, generated.ErrPermissionDenied.Error()) {
		t.Fatalf("post owner without moderator role must not pin, got %v", err)
	}
	_, err = facade.SetPinned(placementContext("persona-moderator", "pin-stale"), PresentationCommand{
		CircleID: "circle-1", PlacementID: "placement-1", ExpectedVersion: 2, Enabled: true,
	})
	if !hasRuntimeCode(err, generated.ErrPlacementVersionConflict.Error()) {
		t.Fatalf("stale version must conflict, got %v", err)
	}
	result, err := facade.SetPinned(placementContext("persona-moderator", "pin-ok"), PresentationCommand{
		CircleID: "circle-1", PlacementID: "placement-1", ExpectedVersion: 1, Enabled: true,
	})
	if err != nil || result.Version != 2 || !store.placement.Pinned {
		t.Fatalf("moderator pin drift: result=%+v placement=%+v err=%v", result, store.placement, err)
	}
}

func hasRuntimeCode(err error, want string) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) && appError.Code.String() == want
}

func placementContext(personaID, idempotencyKey string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "circle.circle_post_placement.PlacePostInCircle",
		RequestID:   "request-1", TraceID: "trace-1", IdempotencyKey: idempotencyKey,
		Actor: operation.ActorContext{AccountID: "account-1", PersonaID: personaID},
	})
}

type contractStore struct {
	placement *placementmodel.CirclePostPlacement
	receipts  map[string]struct {
		digest string
		result placementports.CommitReceipt
	}
}

func newContractStore() *contractStore {
	return &contractStore{receipts: make(map[string]struct {
		digest string
		result placementports.CommitReceipt
	})}
}

func (store *contractStore) Load(_ context.Context, id string) (placementmodel.CirclePostPlacement, bool, error) {
	if store.placement == nil || store.placement.ID != id {
		return placementmodel.CirclePostPlacement{}, false, nil
	}
	return *store.placement, true, nil
}

func (store *contractStore) Commit(_ context.Context, request placementports.CommitRequest) (placementports.CommitReceipt, error) {
	if receipt, found := store.receipts[request.ReceiptKey]; found {
		if receipt.digest != request.CommandDigest {
			return placementports.CommitReceipt{}, placementmodel.ErrIdempotencyConflict
		}
		result := receipt.result
		result.Replayed = true
		return result, nil
	}
	next, _, err := request.Change.Apply(store.placement)
	if err != nil {
		return placementports.CommitReceipt{}, err
	}
	store.placement = &next
	result := placementports.CommitReceipt{PlacementID: next.ID, Version: next.Version, State: next.State}
	store.receipts[request.ReceiptKey] = struct {
		digest string
		result placementports.CommitReceipt
	}{request.CommandDigest, result}
	return result, nil
}

type contractReaders struct {
	circle     placementports.CirclePolicySlice
	group      placementports.GroupPolicySlice
	post       placementports.PostOwnerSlice
	membership placementports.MembershipRoleSlice
}

func (readers contractReaders) policyReaders() placementports.PolicyReaders {
	return placementports.PolicyReaders{Circles: readers, Groups: readers, Posts: readers, Memberships: readers}
}

func (readers contractReaders) ReadCirclePolicy(context.Context, string) (placementports.CirclePolicySlice, bool, error) {
	return readers.circle, readers.circle.CircleID != "", nil
}

func (readers contractReaders) ReadGroupPolicy(context.Context, string) (placementports.GroupPolicySlice, bool, error) {
	return readers.group, readers.group.GroupID != "", nil
}

func (readers contractReaders) ReadPostOwner(context.Context, string) (placementports.PostOwnerSlice, bool, error) {
	return readers.post, readers.post.PostID != "", nil
}

func (readers contractReaders) ReadMembershipRole(context.Context, string, string) (placementports.MembershipRoleSlice, bool, error) {
	return readers.membership, readers.membership.PersonaID != "", nil
}
