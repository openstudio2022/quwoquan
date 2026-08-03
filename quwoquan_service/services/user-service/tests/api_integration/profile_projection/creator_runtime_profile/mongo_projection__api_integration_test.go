package api_integration

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	creatorevent "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/adapters/inbound/event"
	creatorapp "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
	creatorpersistence "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestCreatorRuntimeProfileMongoProjectionAndTombstone(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := creatorpersistence.NewCreatorRuntimeProfileReader(runtime.Database)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("ensure CreatorRuntimeProfile indexes: %v", err)
		}
		handler := creatorevent.NewHandler(creatorapp.NewProjector(store))
		profile := creatorapp.Profile{
			CreatorID: "creator-1", DisplayName: "真实创作者", AvatarURL: "https://assets.test/avatar",
			FollowerCount: 8, PostCount: 3, SourceVersion: 4, UpdatedAt: time.Now().UTC(),
		}
		if applied, err := handler.Apply(ctx, creatorevent.CreatorProfileChanged{
			EventType: "CreatorReleaseActivated", Profile: profile,
		}); err != nil || !applied {
			t.Fatalf("project creator profile: applied=%v err=%v", applied, err)
		}
		if _, found, err := store.FindActiveByPublicIdentity(ctx, profile.CreatorID); err != nil || !found {
			t.Fatalf("read active creator profile: found=%v err=%v", found, err)
		}
		if applied, err := handler.Apply(ctx, creatorevent.CreatorProfileChanged{
			EventType: "CreatorReleaseRetired", CreatorID: profile.CreatorID, Version: 5,
		}); err != nil || !applied {
			t.Fatalf("tombstone creator profile: applied=%v err=%v", applied, err)
		}
		if _, found, err := store.FindActiveByPublicIdentity(ctx, profile.CreatorID); err != nil || found {
			t.Fatalf("tombstoned creator remained public: found=%v err=%v", found, err)
		}
	})
}
