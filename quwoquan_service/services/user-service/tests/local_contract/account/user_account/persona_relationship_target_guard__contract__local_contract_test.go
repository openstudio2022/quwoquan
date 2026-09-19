package local_contract

import (
	"context"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

type fakeRelationshipStore struct {
	applied []relmodel.Command
}

func (s *fakeRelationshipStore) Apply(
	_ context.Context,
	command relmodel.Command,
) (relmodel.MutationResult, error) {
	s.applied = append(s.applied, command)
	return relmodel.MutationResult{
		Changed: true,
		State:   relmodel.RelationshipState{UpdatedAt: time.Now().UTC()},
	}, nil
}

func (s *fakeRelationshipStore) Get(
	_ context.Context,
	_, _ string,
) (relmodel.RelationshipState, error) {
	return relmodel.RelationshipState{}, nil
}

func (s *fakeRelationshipStore) GetMany(
	_ context.Context,
	_ string,
	targetPersonaIDs []string,
) (map[string]relmodel.RelationshipState, error) {
	states := make(map[string]relmodel.RelationshipState, len(targetPersonaIDs))
	for _, targetPersonaID := range targetPersonaIDs {
		states[targetPersonaID] = relmodel.RelationshipState{}
	}
	return states, nil
}

func (s *fakeRelationshipStore) ListFollowing(
	_ context.Context, _, _ string, _ int, _, _ string,
) ([]relmodel.Direction, string, error) {
	return nil, "", nil
}

func (s *fakeRelationshipStore) ListFollowers(
	_ context.Context, _, _ string, _ int, _, _ string,
) ([]relmodel.Direction, string, error) {
	return nil, "", nil
}

func (s *fakeRelationshipStore) ListBlocked(
	_ context.Context, _, _ string, _ int,
) ([]relports.BlockedListItem, string, error) {
	return nil, "", nil
}

type guardBasis struct{}

func (guardBasis) Issue(relationshipapp.MutationBasisClaims) (string, error) {
	return "guard-basis", nil
}
func (guardBasis) Verify(_ string, command relmodel.Command, pair string) (relationshipapp.MutationBasisClaims, error) {
	return relationshipapp.MutationBasisClaims{ActorPersonaID: command.SourcePersonaID, TargetPersonaID: command.TargetPersonaID, PairID: pair, ExpectedVersion: *command.ExpectedVersion, AcceptUntil: time.Now().Add(time.Hour)}, nil
}
func (b guardBasis) VerifyForRecovery(token string, command relmodel.Command, pair string) (relationshipapp.MutationBasisClaims, error) {
	return b.Verify(token, command, pair)
}
func (guardBasis) Digest(string) string { return "guard" }

type guardReceipts struct{}

func (guardReceipts) Recover(context.Context, string, string, relmodel.CommandKind, string) (relmodel.MutationResult, bool, error) {
	return relmodel.MutationResult{}, false, nil
}
func (guardReceipts) FinalizeExpired(context.Context, string, string, relmodel.CommandKind, string, time.Time) (relmodel.MutationResult, error) {
	return relmodel.MutationResult{}, nil
}
func guardEvidence() relationshipapp.CommandEvidence {
	return relationshipapp.CommandEvidence{IdempotencyKey: "guard-key", MutationBasis: "guard-basis", ExpectedVersion: 0}
}

type fakePersonaReader struct {
	personas map[string]*usermodel.Persona
}

func (r *fakePersonaReader) FindByID(_ context.Context, id string) (*usermodel.Persona, error) {
	return r.personas[id], nil
}

func (r *fakePersonaReader) FindByUserID(_ context.Context, _ string) ([]usermodel.Persona, error) {
	return nil, nil
}

func (r *fakePersonaReader) FindActiveByUserID(_ context.Context, _ string) (*usermodel.Persona, error) {
	return nil, nil
}

func (r *fakePersonaReader) FindByUserHandle(_ context.Context, _ string) (*usermodel.Persona, error) {
	return nil, nil
}

func (r *fakePersonaReader) FindByPersonaID(
	_ context.Context,
	personaID string,
) (*usermodel.Persona, error) {
	return r.personas[personaID], nil
}

// TestFollowTargetGuard 锁定 metadata error_codes 契约：
// Follow/Block 前必须证明 target 存在且未退役（USER.RELATIONSHIP.target_not_found，
// 404 掩蔽存在性）；Unfollow 是 unset 幂等清理，目标消失仍允许收敛。
func TestFollowTargetGuard_MissingTargetRejected(t *testing.T) {
	store := &fakeRelationshipStore{}
	personas := &fakePersonaReader{personas: map[string]*usermodel.Persona{}}
	service := relationshipapp.NewPersonaRelationshipService(
		store, personas, nil, nil, relationshipapp.WithMutationBasis(guardBasis{}, guardReceipts{}),
	)

	_, err := service.Follow(
		context.Background(),
		"ps_actor", "ps_missing_target", "", guardEvidence(),
	)
	if err == nil {
		t.Fatal("expected follow against missing target to fail")
	}
	app := rterr.NormalizeError(err)
	if app.Code.Reason != "target_not_found" || app.Code.Kind != "RELATIONSHIP" {
		t.Fatalf("expected USER.RELATIONSHIP.target_not_found, got %+v", app.Code)
	}
	if len(store.applied) != 0 {
		t.Fatalf("missing target must not reach the store, applied=%d", len(store.applied))
	}
}

func TestFollowTargetGuard_RetiredTargetRejected(t *testing.T) {
	store := &fakeRelationshipStore{}
	personas := &fakePersonaReader{personas: map[string]*usermodel.Persona{
		"ps_retired": {PersonaID: "ps_retired", UserID: "owner", Status: "retired"},
	}}
	service := relationshipapp.NewPersonaRelationshipService(
		store, personas, nil, nil, relationshipapp.WithMutationBasis(guardBasis{}, guardReceipts{}),
	)

	_, err := service.Follow(context.Background(), "ps_actor", "ps_retired", "", guardEvidence())
	if err == nil {
		t.Fatal("expected follow against retired target to fail")
	}
	app := rterr.NormalizeError(err)
	if app.Code.Reason != "target_not_found" {
		t.Fatalf("expected target_not_found for retired target, got %+v", app.Code)
	}
}

func TestFollowTargetGuard_ActiveTargetPasses(t *testing.T) {
	store := &fakeRelationshipStore{}
	personas := &fakePersonaReader{personas: map[string]*usermodel.Persona{
		"ps_active": {PersonaID: "ps_active", UserID: "owner", Status: "active"},
		"ps_actor":  {PersonaID: "ps_actor", UserID: "actor", Status: "active"},
	}}
	service := relationshipapp.NewPersonaRelationshipService(
		store, personas, nil, nil, relationshipapp.WithMutationBasis(guardBasis{}, guardReceipts{}),
	)

	if _, err := service.Follow(
		context.Background(), "ps_actor", "ps_active", "", guardEvidence(),
	); err != nil {
		t.Fatalf("active target follow must pass the guard: %v", err)
	}
	if len(store.applied) != 1 {
		t.Fatalf("expected command to reach store, applied=%d", len(store.applied))
	}
}

func TestFollowTargetGuard_UnfollowSkipsExistenceCheck(t *testing.T) {
	store := &fakeRelationshipStore{}
	personas := &fakePersonaReader{personas: map[string]*usermodel.Persona{}}
	service := relationshipapp.NewPersonaRelationshipService(
		store, personas, nil, nil, relationshipapp.WithMutationBasis(guardBasis{}, guardReceipts{}),
	)

	if _, err := service.Unfollow(
		context.Background(), "ps_actor", "ps_gone_target", guardEvidence(),
	); err != nil {
		t.Fatalf("unfollow must converge even when target vanished: %v", err)
	}
	if len(store.applied) != 1 {
		t.Fatalf("expected unfollow to reach store, applied=%d", len(store.applied))
	}
}
