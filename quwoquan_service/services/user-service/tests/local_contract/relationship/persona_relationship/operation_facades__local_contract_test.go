// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: follow-user-local
// readiness_case: unfollow-user-local
// readiness_case: list-following-local
// readiness_case: list-followers-local
// readiness_case: get-relationship-local
// readiness_case: get-relationship-capability-local
// readiness_case: block-user-local
// readiness_case: unblock-user-local
// readiness_case: list-blocked-users-local
package local_contract

import (
	"context"
	"testing"
	"time"

	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

type readinessRelationshipStore struct {
	commands []relmodel.Command
}

func (store *readinessRelationshipStore) Apply(
	_ context.Context,
	command relmodel.Command,
) (relmodel.MutationResult, error) {
	store.commands = append(store.commands, command)
	state := relmodel.RelationshipState{UpdatedAt: time.Now().UTC(), Version: int64(len(store.commands))}
	switch command.Kind {
	case relmodel.CommandFollow:
		state.IsFollowing = true
	case relmodel.CommandBlock:
		state.IsBlocked = true
	}
	return relmodel.MutationResult{Changed: true, State: state}, nil
}

func (store *readinessRelationshipStore) Get(
	_ context.Context,
	_, _ string,
) (relmodel.RelationshipState, error) {
	return relmodel.RelationshipState{IsFollowing: true, UpdatedAt: time.Now().UTC()}, nil
}

func (store *readinessRelationshipStore) ListFollowing(
	_ context.Context,
	sourcePersonaID, _ string,
	_ int,
) ([]relmodel.Direction, string, error) {
	return []relmodel.Direction{{
		SourcePersonaID: sourcePersonaID,
		TargetPersonaID: "target-persona",
		Following:       true,
	}}, "following-next", nil
}

func (store *readinessRelationshipStore) ListFollowers(
	_ context.Context,
	targetPersonaID, _ string,
	_ int,
) ([]relmodel.Direction, string, error) {
	return []relmodel.Direction{{
		SourcePersonaID: "follower-persona",
		TargetPersonaID: targetPersonaID,
		Following:       true,
	}}, "followers-next", nil
}

func (store *readinessRelationshipStore) ListBlocked(
	_ context.Context,
	_, _ string,
	_ int,
) ([]relports.BlockedListItem, string, error) {
	return []relports.BlockedListItem{{TargetPersonaID: "blocked-persona"}}, "blocked-next", nil
}

func TestPersonaRelationshipOperationsCallTheOwningFacade(t *testing.T) {
	ctx := t.Context()
	store := &readinessRelationshipStore{}
	service := relationshipapp.NewPersonaRelationshipService(store, nil, nil, nil)

	if result, err := service.Follow(ctx, "viewer-persona", "target-persona", "homepage", "follow-key"); err != nil || !result.State.IsFollowing {
		t.Fatalf("FollowUser result=%+v err=%v", result, err)
	}
	if result, err := service.Unfollow(ctx, "viewer-persona", "target-persona", "unfollow-key"); err != nil || result.State.IsFollowing {
		t.Fatalf("UnfollowUser result=%+v err=%v", result, err)
	}
	if result, err := service.Block(ctx, "viewer-persona", "target-persona", "block-key"); err != nil || !result.State.IsBlocked {
		t.Fatalf("BlockUser result=%+v err=%v", result, err)
	}
	if result, err := service.Unblock(ctx, "viewer-persona", "target-persona", "unblock-key"); err != nil || result.State.IsBlocked {
		t.Fatalf("UnblockUser result=%+v err=%v", result, err)
	}
	wantKinds := []relmodel.CommandKind{
		relmodel.CommandFollow,
		relmodel.CommandUnfollow,
		relmodel.CommandBlock,
		relmodel.CommandUnblock,
	}
	if len(store.commands) != len(wantKinds) {
		t.Fatalf("relationship commands=%+v", store.commands)
	}
	for index, want := range wantKinds {
		if store.commands[index].Kind != want {
			t.Fatalf("relationship commands=%+v", store.commands)
		}
	}

	state, err := service.GetRelationship(ctx, "viewer-persona", "target-persona")
	if err != nil || !state.IsFollowing {
		t.Fatalf("GetRelationship state=%+v err=%v", state, err)
	}
	following, followingCursor, err := service.ListFollowing(ctx, "viewer-persona", "", 20)
	if err != nil || len(following) != 1 || following[0].TargetPersonaID != "target-persona" || followingCursor != "following-next" {
		t.Fatalf("ListFollowing items=%+v cursor=%q err=%v", following, followingCursor, err)
	}
	followers, followersCursor, err := service.ListFollowers(ctx, "target-persona", "", 20)
	if err != nil || len(followers) != 1 || followers[0].SourcePersonaID != "follower-persona" || followersCursor != "followers-next" {
		t.Fatalf("ListFollowers items=%+v cursor=%q err=%v", followers, followersCursor, err)
	}
	blocked, blockedCursor, err := service.ListBlocked(ctx, "viewer-persona", "", 20)
	if err != nil || len(blocked) != 1 || blocked[0].TargetPersonaID != "blocked-persona" || blockedCursor != "blocked-next" {
		t.Fatalf("ListBlockedUsers items=%+v cursor=%q err=%v", blocked, blockedCursor, err)
	}

	capability := relationshipapp.NewRelationshipCapabilityView(
		relmodel.RelationshipCapabilityFacts{
			ViewerPersonaID: "viewer-persona",
			TargetPersonaID: "target-persona",
			Relationship:    state,
		},
	)
	if capability.RelationState != "following" || capability.CanFollow || !capability.CanUnfollow {
		t.Fatalf("GetRelationshipCapability view=%+v", capability)
	}
}
