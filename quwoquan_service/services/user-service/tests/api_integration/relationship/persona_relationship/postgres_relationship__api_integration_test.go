// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: follow-user-api
// readiness_case: unfollow-user-api
// readiness_case: list-following-api
// readiness_case: list-followers-api
// readiness_case: get-relationship-api
// readiness_case: get-relationship-capability-api
// readiness_case: block-user-api
// readiness_case: unblock-user-api
// readiness_case: list-blocked-users-api
package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestPersonaRelationshipPostgresFollowReplayAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		service := relationshipapp.NewPersonaRelationshipService(
			relationshippersistence.NewPgPersonaRelationshipStore(pool), nil, nil, nil,
		)
		first, err := service.Follow(ctx, "persona-a", "persona-b", "homepage", "relationship-follow-key")
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := service.Follow(ctx, "persona-a", "persona-b", "homepage", "relationship-follow-key")
		if err != nil || !replayed.IdempotentReplay || replayed.State.Version != first.State.Version {
			t.Fatalf("PersonaRelationship replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM persona_relationship_outbox`).Scan(&outboxCount); err != nil || outboxCount != 1 {
			t.Fatalf("PersonaRelationship outbox=%d err=%v", outboxCount, err)
		}
	})
}

func TestPersonaRelationshipPostgresOperationsShareOneAggregate(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		service := relationshipapp.NewPersonaRelationshipService(
			relationshippersistence.NewPgPersonaRelationshipStore(pool), nil, nil, nil,
		)
		if result, err := service.Follow(ctx, "viewer-persona", "target-persona", "homepage", "follow-operation-key"); err != nil || !result.State.IsFollowing {
			t.Fatalf("FollowUser result=%+v err=%v", result, err)
		}
		state, err := service.GetRelationship(ctx, "viewer-persona", "target-persona")
		if err != nil || !state.IsFollowing {
			t.Fatalf("GetRelationship state=%+v err=%v", state, err)
		}
		following, _, err := service.ListFollowing(ctx, "viewer-persona", "", 20)
		if err != nil || len(following) != 1 || following[0].TargetPersonaID != "target-persona" {
			t.Fatalf("ListFollowing items=%+v err=%v", following, err)
		}
		followers, _, err := service.ListFollowers(ctx, "target-persona", "", 20)
		if err != nil || len(followers) != 1 || followers[0].SourcePersonaID != "viewer-persona" {
			t.Fatalf("ListFollowers items=%+v err=%v", followers, err)
		}
		capability := relationshipapp.NewRelationshipCapabilityView(
			relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer-persona",
				TargetPersonaID: "target-persona",
				Relationship:    state,
			},
		)
		if capability.CanFollow || !capability.CanUnfollow {
			t.Fatalf("GetRelationshipCapability view=%+v", capability)
		}
		if result, err := service.Unfollow(ctx, "viewer-persona", "target-persona", "unfollow-operation-key"); err != nil || result.State.IsFollowing {
			t.Fatalf("UnfollowUser result=%+v err=%v", result, err)
		}
		if result, err := service.Block(ctx, "viewer-persona", "target-persona", "block-operation-key"); err != nil || !result.State.IsBlocked {
			t.Fatalf("BlockUser result=%+v err=%v", result, err)
		}
		blocked, _, err := service.ListBlocked(ctx, "viewer-persona", "", 20)
		if err != nil || len(blocked) != 1 || blocked[0].TargetPersonaID != "target-persona" {
			t.Fatalf("ListBlockedUsers items=%+v err=%v", blocked, err)
		}
		if result, err := service.Unblock(ctx, "viewer-persona", "target-persona", "unblock-operation-key"); err != nil || result.State.IsBlocked {
			t.Fatalf("UnblockUser result=%+v err=%v", result, err)
		}
		var receiptCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM persona_relationship_command_receipts`).Scan(&receiptCount); err != nil || receiptCount != 4 {
			t.Fatalf("PersonaRelationship receipts=%d err=%v", receiptCount, err)
		}
	})
}
