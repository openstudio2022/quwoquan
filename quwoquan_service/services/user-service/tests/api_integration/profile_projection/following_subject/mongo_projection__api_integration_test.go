package api_integration

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	followingevent "quwoquan_service/services/user-service/internal/profile_projection/following_subject/adapters/inbound/event"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
	followingpersistence "quwoquan_service/services/user-service/internal/profile_projection/following_subject/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestFollowingSubjectMongoProjectionIsMonotonic(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := followingpersistence.NewMongoFollowingSubjectStore(runtime.Database)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("ensure FollowingSubject indexes: %v", err)
		}
		handler := followingevent.NewHandler(followingapp.NewProjector(store))
		event := followingapp.FollowChangedEvent{
			EventID: "follow-event-2", ViewerPersonaID: "persona-viewer",
			SubjectType: "homepage", SubjectID: "homepage-1", Following: true,
			OccurredAt: time.Now().UTC(), SourceVersion: 2,
		}
		if err := handler.Apply(ctx, event); err != nil {
			t.Fatalf("apply FollowingSubject event: %v", err)
		}
		stale := event
		stale.EventID, stale.SourceVersion, stale.Following = "follow-event-1", 1, false
		if err := handler.Apply(ctx, stale); err != nil {
			t.Fatalf("stale FollowingSubject event: %v", err)
		}
		rows, err := store.List(ctx, event.ViewerPersonaID, event.SubjectType, 10)
		if err != nil || len(rows) != 1 || rows[0].SourceVersion != 2 {
			t.Fatalf("projection regressed: rows=%+v err=%v", rows, err)
		}
	})
}
