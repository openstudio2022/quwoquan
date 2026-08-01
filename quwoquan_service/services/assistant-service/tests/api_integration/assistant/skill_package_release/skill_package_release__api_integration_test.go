// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
package skill_package_release_integration

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	skillpackagepersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/persistence"
)

const integrationSkillPackageID = "assistant.session.skills"

type integrationAssetReader map[string][]byte

func (reader integrationAssetReader) ReadAsset(
	_ context.Context,
	locator string,
) ([]byte, error) {
	value, found := reader[locator]
	if !found {
		return nil, fmt.Errorf("asset %q not found", locator)
	}
	return append([]byte(nil), value...), nil
}

func TestSkillPackageMongoActivationSurvivesRestartAndRollsBackAtomically(
	t *testing.T,
) {
	if skillPackageDB == nil {
		t.Fatal("skill package MongoDB was not initialized")
	}
	if err := skillPackageDB.Drop(t.Context()); err != nil {
		t.Fatal(err)
	}
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	assets := integrationAssetReader{}
	releaseOne := integrationRelease(t, assets, "1.0.0", privateKey)
	releaseTwo := integrationRelease(t, assets, "1.1.0", privateKey)
	now := time.Date(2026, 7, 31, 20, 0, 0, 0, time.UTC)
	newService := func() *application.Service {
		store := skillpackagepersistence.NewMongoStore(skillPackageDB)
		if indexErr := store.EnsureIndexes(t.Context()); indexErr != nil {
			t.Fatal(indexErr)
		}
		return application.NewService(
			store,
			store,
			assets,
			application.NewEd25519Verifier(
				map[string]ed25519.PublicKey{"integration-key": publicKey},
			),
			application.RuntimeIdentity{
				APIVersion: "assistant-skill/v1",
				Version:    "1.4.0",
			},
			func() time.Time {
				now = now.Add(time.Second)
				return now
			},
		)
	}
	service := newService()
	if _, err := service.Stage(t.Context(), "stage-one", releaseOne); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Stage(t.Context(), "stage-two", releaseTwo); err != nil {
		t.Fatal(err)
	}
	first, err := service.Activate(t.Context(), "activate-one", application.ActivateInput{
		PackageID:        integrationSkillPackageID,
		ReleaseDigest:    releaseOne.ReleaseDigest,
		ExpectedRevision: 0,
		ActivatedBy:      "service:integration-publisher",
	})
	if err != nil {
		t.Fatal(err)
	}
	replayed, err := service.Activate(t.Context(), "activate-one", application.ActivateInput{
		PackageID:        integrationSkillPackageID,
		ReleaseDigest:    releaseOne.ReleaseDigest,
		ExpectedRevision: 0,
		ActivatedBy:      "service:integration-publisher",
	})
	if err != nil || !replayed.Replayed ||
		replayed.Activation != first.Activation {
		t.Fatalf("activation replay=%+v err=%v", replayed, err)
	}

	// Recreate all stateful adapters to prove the active pointer and immutable
	// release are authoritative Mongo state rather than process cache.
	service = newService()
	activeOne, err := service.ResolveActive(t.Context(), integrationSkillPackageID)
	if err != nil || activeOne.Release.ReleaseDigest != releaseOne.ReleaseDigest {
		t.Fatalf("active release after restart=%+v err=%v", activeOne.Release, err)
	}
	if _, err := service.Activate(t.Context(), "activate-two", application.ActivateInput{
		PackageID:        integrationSkillPackageID,
		ReleaseDigest:    releaseTwo.ReleaseDigest,
		ExpectedRevision: 1,
		ActivatedBy:      "service:integration-publisher",
	}); err != nil {
		t.Fatal(err)
	}
	rolledBack, err := service.Rollback(
		t.Context(),
		"rollback-two",
		application.RollbackInput{
			PackageID:        integrationSkillPackageID,
			ExpectedRevision: 2,
			ActivatedBy:      "service:integration-publisher",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if rolledBack.Activation.ActiveReleaseDigest != releaseOne.ReleaseDigest ||
		rolledBack.Activation.PreviousReleaseDigest != releaseTwo.ReleaseDigest ||
		rolledBack.Activation.Revision != 3 {
		t.Fatalf("rollback=%+v", rolledBack)
	}

	service = newService()
	activeAfterRollback, err := service.ResolveActive(
		t.Context(),
		integrationSkillPackageID,
	)
	if err != nil ||
		activeAfterRollback.Release.ReleaseDigest != releaseOne.ReleaseDigest ||
		activeAfterRollback.Release.Status != model.StatusActive {
		t.Fatalf(
			"active release after rollback=%+v err=%v",
			activeAfterRollback.Release,
			err,
		)
	}
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_releases",
		bson.M{"packageId": integrationSkillPackageID},
		2,
	)
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_activations",
		bson.M{"packageId": integrationSkillPackageID, "revision": 3},
		1,
	)
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_command_receipts",
		bson.M{"packageId": integrationSkillPackageID},
		5,
	)
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_outbox",
		bson.M{"packageId": integrationSkillPackageID},
		3,
	)
}

func integrationRelease(
	t *testing.T,
	assets integrationAssetReader,
	version string,
	privateKey ed25519.PrivateKey,
) model.Release {
	t.Helper()
	kinds := []string{
		model.AssetManifest,
		model.AssetPrompt,
		model.AssetActivation,
		model.AssetContext,
		model.AssetCapability,
		model.AssetPresentation,
		model.AssetEvaluation,
		model.AssetReplay,
	}
	descriptors := make([]model.Asset, 0, len(kinds))
	for _, kind := range kinds {
		locator := "artifact://integration/" + version + "/" + kind
		content := []byte(version + ":" + kind)
		assets[locator] = content
		sum := sha256.Sum256(content)
		descriptors = append(descriptors, model.Asset{
			AssetID:     version + "." + kind,
			Kind:        kind,
			Locator:     locator,
			AssetDigest: "sha256:" + hex.EncodeToString(sum[:]),
		})
	}
	release := model.Release{
		PackageID:      integrationSkillPackageID,
		PackageVersion: version,
		ReleaseDigest:  "sha256:" + strings.Repeat("0", 64),
		Assets:         descriptors,
		RuntimeCompatibility: model.RuntimeCompatibility{
			APIVersion:            "assistant-skill/v1",
			MinimumRuntimeVersion: "1.0.0",
			MaximumRuntimeVersion: "1.9.9",
		},
		Provenance: model.Provenance{
			SourceRepository: "https://example.invalid/quwoquan",
			SourceRevision:   "revision-" + version,
			BuildID:          "build-" + version,
			BuiltAt: time.Date(
				2026,
				7,
				31,
				19,
				0,
				0,
				0,
				time.UTC,
			),
		},
		Signature: model.Signature{
			Algorithm: "ed25519",
			KeyID:     "integration-key",
			Value:     "pending",
		},
		CapabilityGrants: []model.CapabilityGrant{
			{CapabilityID: "context.trip", Scope: "read_with_consent"},
			{CapabilityID: "tool.web_search", Scope: "read_public"},
		},
	}
	digest, err := model.Digest(release)
	if err != nil {
		t.Fatal(err)
	}
	release.ReleaseDigest = digest
	release.Signature.Value = base64.StdEncoding.EncodeToString(
		ed25519.Sign(privateKey, []byte(digest)),
	)
	return release
}

func assertSkillPackageDocumentCount(
	t *testing.T,
	collection string,
	filter bson.M,
	want int64,
) {
	t.Helper()
	count, err := skillPackageDB.Collection(collection).CountDocuments(
		t.Context(),
		filter,
	)
	if err != nil || count != want {
		t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
	}
}
