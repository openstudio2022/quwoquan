package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	subjectapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
	subjectpersistence "quwoquan_service/services/user-service/internal/relationship/subject_follow/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestSubjectFollowPostgresReplayAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		service := subjectapp.NewSubjectFollowService(subjectpersistence.NewPgSubjectFollowStore(pool))
		command := subjectapp.FollowSubjectCommand{
			PersonaID: "subject-viewer", SubjectType: "homepage", SubjectID: "homepage-1",
			Source: "homepage", IdempotencyKey: "subject-follow-key",
		}
		first, err := service.Follow(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := service.Follow(ctx, command)
		if err != nil || !replayed.IdempotentReplay || replayed.Follow.Version != first.Follow.Version {
			t.Fatalf("SubjectFollow replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM subject_follow_outbox`).Scan(&outboxCount); err != nil || outboxCount != 1 {
			t.Fatalf("SubjectFollow outbox=%d err=%v", outboxCount, err)
		}
	})
}
