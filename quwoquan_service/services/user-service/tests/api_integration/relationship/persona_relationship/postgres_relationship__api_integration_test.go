package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
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
