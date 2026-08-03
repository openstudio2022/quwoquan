package api_integration

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	visitpersistence "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestFollowedSubjectVisitStateMongoWatermarkAndReceipt(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := visitpersistence.NewMongoFollowedSubjectVisitStore(runtime.Database)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("ensure visit state indexes: %v", err)
		}
		service := visitapp.NewVisitService(store, nil)
		visitedAt := time.Now().UTC().Truncate(time.Millisecond)
		input := visitapp.MarkVisitedInput{
			PersonaID: "persona-viewer", SubjectType: "homepage", SubjectID: "homepage-1",
			VisitedAt: visitedAt, ClientRequestID: "visit-request-1",
		}
		first, err := service.MarkVisited(ctx, input)
		if err != nil {
			t.Fatalf("mark visited: %v", err)
		}
		replayed, err := service.MarkVisited(ctx, input)
		if err != nil || !replayed.Replayed || !replayed.LastVisitedAt.Equal(first.LastVisitedAt) {
			t.Fatalf("visit receipt replay drifted: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		older := input
		older.ClientRequestID, older.VisitedAt = "visit-request-2", visitedAt.Add(-time.Hour)
		result, err := service.MarkVisited(ctx, older)
		if err != nil || !result.LastVisitedAt.Equal(first.LastVisitedAt) {
			t.Fatalf("visit watermark regressed: result=%+v err=%v", result, err)
		}
	})
}
