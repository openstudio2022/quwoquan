package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
	creatorpersistence "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestCreatorReleaseCandidatesCoexistAndReadByExactFence(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := creatorpersistence.NewCreatorReleaseCandidateStore(runtime.Database)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatal(err)
		}
		firstIdentity := candidateIdentity("release-a", candidateDigest("a"))
		secondIdentity := candidateIdentity("release-b", candidateDigest("b"))
		firstState, firstProjection := candidateFixture(t, firstIdentity, "Creator A")
		secondState, secondProjection := candidateFixture(t, secondIdentity, "Creator B")
		if replayed, err := store.Stage(ctx, firstState, []model.CreatorReleaseProjection{firstProjection}); err != nil || replayed {
			t.Fatalf("stage A replayed=%v err=%v", replayed, err)
		}
		if replayed, err := store.Stage(ctx, secondState, []model.CreatorReleaseProjection{secondProjection}); err != nil || replayed {
			t.Fatalf("stage B replayed=%v err=%v", replayed, err)
		}
		if replayed, err := store.Stage(ctx, firstState, []model.CreatorReleaseProjection{firstProjection}); err != nil || !replayed {
			t.Fatalf("exact replay replayed=%v err=%v", replayed, err)
		}
		// 同一 tuple 的二次导入必然带新的 verifiedAt 与派生 closureDigest；
		// 载荷未变即为精确重放，不得判为 drift。
		laterState, laterProjection := candidateFixtureAt(t, firstIdentity, "Creator A", time.Date(2026, 9, 6, 6, 0, 0, 0, time.UTC))
		if replayed, err := store.Stage(ctx, laterState, []model.CreatorReleaseProjection{laterProjection}); err != nil || !replayed {
			t.Fatalf("replay with a later verification clock replayed=%v err=%v", replayed, err)
		}
		if readback, found, err := store.ReadVerifiedCandidate(ctx, firstIdentity); err != nil || !found || !readback.VerifiedAt.Equal(firstState.VerifiedAt) {
			t.Fatalf("replay must keep the first stored attestation: found=%v verifiedAt=%v err=%v", found, readback.VerifiedAt, err)
		}
		mutatedReplay := firstProjection
		mutatedReplay.Profile.DisplayName = "Replay Drift"
		mutatedDigest, digestErr := creatorpersistence.DocumentDigest(mutatedReplay, "documentDigest")
		if digestErr != nil {
			t.Fatal(digestErr)
		}
		mutatedReplay.DocumentDigest = mutatedDigest
		mutatedState := firstState
		mutatedState.ClosureDigest = creatorpersistence.ClosureDigest([]string{mutatedReplay.CreatorID + "=" + mutatedDigest})
		if _, err := store.Stage(ctx, mutatedState, []model.CreatorReleaseProjection{mutatedReplay}); err == nil {
			t.Fatal("same tuple replay with changed payload was accepted")
		}
		for identity, displayName := range map[model.ReleaseIdentity]string{firstIdentity: "Creator A", secondIdentity: "Creator B"} {
			profile, found, err := store.FindByExactContentFence(ctx, identity, "creator-shared")
			if err != nil || !found || profile.DisplayName != displayName {
				t.Fatalf("exact fence read %+v: found=%v profile=%+v err=%v", identity, found, profile, err)
			}
		}
		wrong := firstIdentity
		wrong.ManifestDigest = candidateDigest("c")
		if _, found, err := store.FindByExactContentFence(ctx, wrong, "creator-shared"); err != nil || found {
			t.Fatalf("wrong tuple must be not_found: found=%v err=%v", found, err)
		}
	})
}

func TestCreatorReleaseCandidateClosureDriftFailsClosed(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := creatorpersistence.NewCreatorReleaseCandidateStore(runtime.Database)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatal(err)
		}
		identity := candidateIdentity("release-drift", candidateDigest("d"))
		state, projection := candidateFixture(t, identity, "Original")
		if _, err := store.Stage(ctx, state, []model.CreatorReleaseProjection{projection}); err != nil {
			t.Fatal(err)
		}
		_, err := runtime.Database.Collection("creator_release_projections").UpdateOne(ctx, bson.M{"environment": identity.Environment, "sourceOwner": identity.SourceOwner, "releaseId": identity.ReleaseID, "manifestDigest": identity.ManifestDigest, "creatorId": "creator-shared"}, bson.M{"$set": bson.M{"profile.displayName": "Tampered"}})
		if err != nil {
			t.Fatal(err)
		}
		if _, _, err := store.ReadVerifiedCandidate(ctx, identity); err == nil {
			t.Fatal("closure drift was accepted")
		}
	})
}

func candidateFixture(t *testing.T, identity model.ReleaseIdentity, displayName string) (model.CreatorReleaseCandidateState, model.CreatorReleaseProjection) {
	t.Helper()
	return candidateFixtureAt(t, identity, displayName, time.Date(2026, 9, 6, 5, 0, 0, 0, time.UTC))
}

func candidateFixtureAt(t *testing.T, identity model.ReleaseIdentity, displayName string, verifiedAt time.Time) (model.CreatorReleaseCandidateState, model.CreatorReleaseProjection) {
	t.Helper()
	profileDigest := candidateDigest("e")
	profile := model.CreatorRuntimeProfile{CreatorID: "creator-shared", PersonaID: "author-shared", DisplayName: displayName, PackageDigest: identity.ManifestDigest, ReleaseID: identity.ReleaseID, Status: "candidate", ManagedBy: "qwq_data", ImportedAt: verifiedAt, UpdatedAt: verifiedAt}
	projection := model.CreatorReleaseProjection{ReleaseIdentity: identity, CreatorID: profile.CreatorID, PersonaID: profile.PersonaID, Profile: profile, AuthorID: "author-shared", ProfileDigest: profileDigest, ProjectionVersion: 1, VerifiedAt: verifiedAt}
	digest, err := creatorpersistence.DocumentDigest(projection, "documentDigest")
	if err != nil {
		t.Fatal(err)
	}
	projection.DocumentDigest = digest
	state := model.CreatorReleaseCandidateState{ReleaseIdentity: identity, Status: "verified", ProjectionVersion: 1, VerifiedAt: verifiedAt, ClosureDigest: creatorpersistence.ClosureDigest([]string{projection.CreatorID + "=" + digest}), ExpectedCount: 1, ProjectedCount: 1, AuthorIDs: []string{"author-shared"}, ProfileDigests: []model.CreatorProfileDigestBinding{{CreatorID: projection.CreatorID, AuthorID: projection.AuthorID, Digest: profileDigest}}}
	return state, projection
}

func candidateIdentity(releaseID, digest string) model.ReleaseIdentity {
	return model.ReleaseIdentity{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: releaseID, ManifestDigest: digest}
}
func candidateDigest(character string) string {
	value := "sha256:"
	for len(value) < len("sha256:")+64 {
		value += character
	}
	return value
}
