package api_integration

import (
	"context"
	"strings"
	"testing"
	"time"

	relapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relpersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
)

func testRelationshipSigner(t *testing.T) *relpersistence.MutationBasisSigner {
	t.Helper()
	signer, err := relpersistence.NewMutationBasisSigner("user-service.test", "test-key", []relpersistence.MutationBasisKey{{ID: "test-key", Material: []byte(strings.Repeat("k", 32))}})
	if err != nil {
		t.Fatal(err)
	}
	return signer
}
func relationshipEvidence(t *testing.T, ctx context.Context, service *relapp.PersonaRelationshipService, actor, target, key string, _ relmodel.CommandKind) relapp.CommandEvidence {
	t.Helper()
	basis, version, _, err := service.IssueMutationBasis(ctx, actor, target)
	if err != nil {
		t.Fatal(err)
	}
	return relapp.CommandEvidence{IdempotencyKey: key, MutationBasis: basis, ExpectedVersion: version}
}
func relationshipServiceForTest(t *testing.T, store *relpersistence.PgPersonaRelationshipStore) *relapp.PersonaRelationshipService {
	t.Helper()
	signer := testRelationshipSigner(t)
	return relapp.NewPersonaRelationshipService(store, nil, nil, nil, relapp.WithMutationBasis(signer, store))
}

func followRelationship(t *testing.T, ctx context.Context, service *relapp.PersonaRelationshipService, actor, target, source, key string) (relmodel.MutationResult, error) {
	t.Helper()
	return service.Follow(ctx, actor, target, source, relationshipEvidence(t, ctx, service, actor, target, key, relmodel.CommandFollow))
}
func unfollowRelationship(t *testing.T, ctx context.Context, service *relapp.PersonaRelationshipService, actor, target, key string) (relmodel.MutationResult, error) {
	t.Helper()
	return service.Unfollow(ctx, actor, target, relationshipEvidence(t, ctx, service, actor, target, key, relmodel.CommandUnfollow))
}
func blockRelationship(t *testing.T, ctx context.Context, service *relapp.PersonaRelationshipService, actor, target, key string) (relmodel.MutationResult, error) {
	t.Helper()
	return service.Block(ctx, actor, target, relationshipEvidence(t, ctx, service, actor, target, key, relmodel.CommandBlock))
}
func unblockRelationship(t *testing.T, ctx context.Context, service *relapp.PersonaRelationshipService, actor, target, key string) (relmodel.MutationResult, error) {
	t.Helper()
	return service.Unblock(ctx, actor, target, relationshipEvidence(t, ctx, service, actor, target, key, relmodel.CommandUnblock))
}

var _ = time.Second

func followWithEvidence(ctx context.Context, service *relapp.PersonaRelationshipService, actor, target, source string, evidence relapp.CommandEvidence) (relmodel.MutationResult, error) {
	return service.Follow(ctx, actor, target, source, evidence)
}
func unfollowWithEvidence(ctx context.Context, service *relapp.PersonaRelationshipService, actor, target string, evidence relapp.CommandEvidence) (relmodel.MutationResult, error) {
	return service.Unfollow(ctx, actor, target, evidence)
}
