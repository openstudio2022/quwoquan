package local_contract

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

type mutableActiveReleaseLoader struct {
	identity application.HomepageReleaseIdentity
	found    bool
	err      error
}

func (loader *mutableActiveReleaseLoader) LoadActiveRelease(context.Context) (application.HomepageReleaseIdentity, bool, error) {
	return loader.identity, loader.found, loader.err
}

func releaseImportedSightInput(title string) application.ImportedHomepageInput {
	return application.ImportedHomepageInput{
		EntityRef: "地点/景区/" + title, Title: title, HomepageType: "sight", City: "阿坝",
		IntroductionMarkdown: "# " + title,
		IntroductionAssets: []application.HomepageIntroductionAsset{{
			AssetID: title + "_cover", URL: "https://media.example/" + title + ".jpg", Role: "cover",
		}},
		CategoryTags: []string{"Entity/地点/景区"},
		PrimarySource: &application.HomepageSource{
			SourceKind: "wikipedia", SourceURL: "https://zh.wikipedia.org/wiki/" + title,
			Title: title, FetchedAt: "2026-09-01T00:00:00Z", SnapshotHash: "sha256:" + strings.Repeat("c", 64),
			PolicyRevision: "encyclopedia-primary", SourceUseMode: "licensed_adaptation",
		},
		SourceURLs: []string{"https://zh.wikipedia.org/wiki/" + title},
	}
}

func releaseIdentity(releaseID, digit string) application.HomepageReleaseIdentity {
	return application.HomepageReleaseIdentity{
		Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: releaseID,
		ManifestDigest: "sha256:" + strings.Repeat(digit, 64),
	}
}

func stageRelease(
	t *testing.T,
	service *application.HomepageService,
	identity application.HomepageReleaseIdentity,
	input application.ImportedHomepageInput,
	now time.Time,
) application.HomepageReleaseStageReport {
	t.Helper()
	report, err := service.StageHomepageReleaseCandidate(t.Context(), application.HomepageReleaseStageRequest{
		Identity: identity, Inputs: []application.ImportedHomepageInput{input},
	}, now)
	if err != nil {
		t.Fatalf("stage %s: %v", identity.ReleaseID, err)
	}
	return report
}

func TestHomepageReleaseStageUsesContentFenceAndPreservesClaimedOverlay(t *testing.T) {
	ctx := context.Background()
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		t.Fatal(err)
	}
	loader := &mutableActiveReleaseLoader{identity: releaseIdentity("release-a", "a"), found: true}
	service := application.NewHomepageServiceWithStore(ctx, store, application.WithActiveReleaseLoader(loader))

	inputA := releaseImportedSightInput("九寨沟")
	inputA.IntroductionMarkdown = "# A\n\nA 正文"
	a := stageRelease(t, service, loader.identity, inputA, time.Date(2026, 9, 6, 1, 0, 0, 0, time.UTC))
	homepageID := a.EntityRefToHomepageID[inputA.EntityRef]

	// Stage creates only a stable published identity shell; release-owned fields
	// stay in the separate exact projection and do not enter governance candidate.
	shell, found, err := store.Load(ctx, homepageID)
	if err != nil || !found || string(shell.Status()) != "published" {
		t.Fatalf("stable release shell missing: found=%t err=%v", found, err)
	}

	inputB := inputA
	inputB.IntroductionMarkdown = "# B\n\nB 正文"
	inputB.City = "成都"
	identityB := releaseIdentity("release-b", "b")
	stageRelease(t, service, identityB, inputB, time.Date(2026, 9, 6, 2, 0, 0, 0, time.UTC))

	visibleA, err := service.GetHomepage(ctx, homepageID)
	if err != nil || !strings.Contains(visibleA.IntroductionMarkdown, "A 正文") {
		t.Fatalf("B staged before fence switch must keep A visible: homepage=%+v err=%v", visibleA, err)
	}

	if err := service.ApplyClaimRequestedProjection(ctx, "claim-request", homepageID); err != nil {
		t.Fatal(err)
	}
	if err := service.ApplyClaimReviewedProjection(ctx, "claim-approved", homepageID, "owner-persona", true); err != nil {
		t.Fatal(err)
	}
	ownerCtx := operation.WithContext(ctx, operation.Context{
		OperationID: "entity.homepage.UpdateClaimedHomepageBasics", RequestID: "release-owner",
		TraceID: "release-owner", IdempotencyKey: "release-owner-update",
		Actor: operation.ActorContext{PersonaID: "owner-persona"},
	})
	if _, err := service.UpdateClaimedHomepageBasics(ownerCtx, homepageID, application.HomepageBasicInput{
		Title: "认领标题", City: "认领城市", CoverURL: "https://claimed.example/cover.jpg",
	}); err != nil {
		t.Fatal(err)
	}

	loader.identity = identityB
	visibleB, err := service.GetHomepage(ctx, homepageID)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(visibleB.IntroductionMarkdown, "B 正文") || visibleB.Title != "认领标题" ||
		visibleB.City != "认领城市" || visibleB.CoverURL != "https://claimed.example/cover.jpg" ||
		visibleB.OwnerPersonaID != "owner-persona" || visibleB.ClaimStatus != "claimed" {
		t.Fatalf("Content switch must select B while preserving claimed overlay: %+v", visibleB)
	}
}

func TestHomepageReleaseProjectionIsPublicWithoutGovernanceCandidateAggregate(t *testing.T) {
	ctx := context.Background()
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		t.Fatal(err)
	}
	identity := releaseIdentity("release-only", "d")
	loader := &mutableActiveReleaseLoader{identity: identity, found: true}
	service := application.NewHomepageServiceWithStore(ctx, store, application.WithActiveReleaseLoader(loader))
	input := releaseImportedSightInput("都江堰")
	report := stageRelease(t, service, identity, input, time.Date(2026, 9, 6, 2, 30, 0, 0, time.UTC))
	homepageID := report.EntityRefToHomepageID[input.EntityRef]
	view, err := service.GetHomepage(ctx, homepageID)
	if err != nil || view.Title != "都江堰" || view.SourceReleaseID != "release-only" || view.Status != "published" {
		t.Fatalf("projection-only public read=%+v err=%v", view, err)
	}
}

func TestHomepageReleaseCandidateReplayDriftWrongManifestAndNotFound(t *testing.T) {
	service, _ := homepagepersistence.NewMemoryHomepageStore()
	identity := releaseIdentity("release-a", "a")
	input := releaseImportedSightInput("黄龙")
	now := time.Date(2026, 9, 6, 3, 0, 0, 0, time.UTC)
	first, err := homepageapp.StageReleaseCandidate(t.Context(), service, homepageapp.ReleaseStageRequest{
		Identity: identity, Inputs: []homepageapp.ImportedInput{input},
	}, now)
	if err != nil || first.Replayed {
		t.Fatalf("first stage=%+v err=%v", first, err)
	}
	replay, err := homepageapp.StageReleaseCandidate(t.Context(), service, homepageapp.ReleaseStageRequest{
		Identity: identity, Inputs: []homepageapp.ImportedInput{input},
	}, now.Add(time.Hour))
	if err != nil || !replay.Replayed || replay.ClosureDigest != first.ClosureDigest || replay.ProjectionVersion != first.ProjectionVersion {
		t.Fatalf("same tuple replay=%+v err=%v", replay, err)
	}
	drift := input
	drift.IntroductionMarkdown += "\n漂移"
	if _, err := homepageapp.StageReleaseCandidate(t.Context(), service, homepageapp.ReleaseStageRequest{
		Identity: identity, Inputs: []homepageapp.ImportedInput{drift},
	}, now); err == nil {
		t.Fatal("same tuple payload drift was accepted")
	}
	wrongManifest, err := homepageapp.QueryReleaseCandidate(t.Context(), service, releaseIdentity("release-a", "9"))
	if err != nil || wrongManifest.Status != "not_found" {
		t.Fatalf("wrong manifest must be exact not_found: receipt=%+v err=%v", wrongManifest, err)
	}
	found, err := homepageapp.QueryReleaseCandidate(t.Context(), service, identity)
	if err != nil || found.Status != "found" || found.Counts == nil || found.Counts.Expected != 1 ||
		found.Counts.Projected != 1 || found.EntityRefMappingDigest == "" || found.ClosureDigest == "" ||
		found.VerifiedAt == nil || found.ProjectionVersion <= 0 {
		t.Fatalf("candidate receipt incomplete: %+v err=%v", found, err)
	}
	raw, _ := json.Marshal(wrongManifest)
	for _, foundOnly := range []string{"projectionVersion", "verifiedAt", "closureDigest", "counts", "entityRefMappingDigest"} {
		if strings.Contains(string(raw), `"`+foundOnly+`"`) {
			t.Fatalf("not_found receipt exposed %s: %s", foundOnly, raw)
		}
	}
}

func TestHomepageReleaseCandidateReceiptIsCreateOnce(t *testing.T) {
	path := filepath.Join(t.TempDir(), "candidate.json")
	receipt := application.HomepageReleaseCandidateReceipt{
		Schema: homepageapp.HomepageReleaseCandidateReceiptSchema,
		Status: "not_found",
		Identity: homepageapp.HomepageReleaseCandidateReceiptIdentity{
			Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "missing",
			ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		},
	}
	if err := homepageimport.WriteHomepageReleaseCandidateReceipt(path, receipt); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := homepageimport.WriteHomepageReleaseCandidateReceipt(path, receipt); err == nil {
		t.Fatal("O_EXCL receipt path was overwritten")
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("existing receipt changed")
	}
}
