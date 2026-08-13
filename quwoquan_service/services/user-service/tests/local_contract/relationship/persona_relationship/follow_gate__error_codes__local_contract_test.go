package local_contract

import (
	"context"
	"errors"
	"testing"

	runtimeerrors "quwoquan_service/runtime/errors"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// blockedRelationshipStore 模拟存量关系中存在 block 方向,follow 提交被拒。
type blockedRelationshipStore struct {
	readinessRelationshipStore
}

func (store *blockedRelationshipStore) Apply(
	context.Context,
	relmodel.Command,
) (relmodel.MutationResult, error) {
	return relmodel.MutationResult{}, relmodel.ErrFollowBlocked
}

func TestFollowSurfacesFollowBlockedWhenBlockDirectionExists(t *testing.T) {
	service := relationshipapp.NewPersonaRelationshipService(
		&blockedRelationshipStore{}, nil, nil, nil,
	)

	_, err := service.Follow(
		t.Context(),
		"viewer-persona",
		"blocked-target-persona",
		"homepage",
		"follow-blocked-key",
	)
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) ||
		appErr.Code.String() != "USER.RELATIONSHIP.follow_blocked" {
		t.Fatalf("expected USER.RELATIONSHIP.follow_blocked, got %T: %v", err, err)
	}
}
