// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
// readiness_case: stage-assistant-skill-package-release-api
// readiness_case: activate-assistant-skill-package-release-api
// readiness_case: rollback-assistant-skill-package-release-api
package skill_package_release_integration

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	packagehttp "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	packageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
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

	resourceRoot := t.TempDir()
	releaseThree := integrationResourceRelease(t, resourceRoot, "1.2.0", privateKey)
	releaseFour := integrationResourceRelease(t, resourceRoot, "1.3.0", privateKey)
	resourceReader, err := packageartifact.NewResourceReader(resourceRoot)
	if err != nil {
		t.Fatalf("construct production immutable asset reader: %v", err)
	}
	store := skillpackagepersistence.NewMongoStore(skillPackageDB)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure HTTP package indexes: %v", err)
	}
	httpService := application.NewService(
		store,
		store,
		resourceReader,
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
	mux := http.NewServeMux()
	packagehttp.NewHandler(httpService).RegisterRoutes(mux)
	stagedHTTP := skillPackageRequest(
		t,
		mux,
		"stage-three-http",
		"service:integration-publisher",
		"/internal/assistant/skill-package-releases",
		releaseThree,
	)
	if stagedHTTP.Code != http.StatusCreated {
		t.Fatalf("HTTP stage status=%d body=%s", stagedHTTP.Code, stagedHTTP.Body.String())
	}
	var stagedRelease model.Release
	if err := json.Unmarshal(stagedHTTP.Body.Bytes(), &stagedRelease); err != nil {
		t.Fatalf("decode HTTP stage response: %v", err)
	}
	if stagedRelease.ReleaseDigest != releaseThree.ReleaseDigest ||
		stagedRelease.PackageVersion != "1.2.0" {
		t.Fatalf("HTTP staged release=%+v", stagedRelease)
	}
	stagedFourthHTTP := skillPackageRequest(
		t,
		mux,
		"stage-four-http",
		"service:integration-publisher",
		"/internal/assistant/skill-package-releases",
		releaseFour,
	)
	if stagedFourthHTTP.Code != http.StatusCreated {
		t.Fatalf("HTTP stage fourth status=%d body=%s", stagedFourthHTTP.Code, stagedFourthHTTP.Body.String())
	}

	activatedHTTP := skillPackageRequest(
		t,
		mux,
		"activate-three-http",
		"service:integration-publisher",
		"/internal/assistant/skill-package-releases:activate",
		map[string]any{
			"packageId":        integrationSkillPackageID,
			"releaseDigest":    releaseThree.ReleaseDigest,
			"expectedRevision": 3,
		},
	)
	if activatedHTTP.Code != http.StatusOK {
		t.Fatalf("HTTP activate status=%d body=%s", activatedHTTP.Code, activatedHTTP.Body.String())
	}
	var activatedHTTPResult model.Activation
	if err := json.Unmarshal(activatedHTTP.Body.Bytes(), &activatedHTTPResult); err != nil {
		t.Fatalf("decode HTTP activate response: %v", err)
	}
	if activatedHTTPResult.ActiveReleaseDigest != releaseThree.ReleaseDigest ||
		activatedHTTPResult.Revision != 4 {
		t.Fatalf("HTTP activation=%+v", activatedHTTPResult)
	}
	activatedFourthHTTP := skillPackageRequest(
		t,
		mux,
		"activate-four-http",
		"service:integration-publisher",
		"/internal/assistant/skill-package-releases:activate",
		map[string]any{
			"packageId":        integrationSkillPackageID,
			"releaseDigest":    releaseFour.ReleaseDigest,
			"expectedRevision": 4,
		},
	)
	if activatedFourthHTTP.Code != http.StatusOK {
		t.Fatalf("HTTP activate fourth status=%d body=%s", activatedFourthHTTP.Code, activatedFourthHTTP.Body.String())
	}
	var activatedFourthResult model.Activation
	if err := json.Unmarshal(activatedFourthHTTP.Body.Bytes(), &activatedFourthResult); err != nil {
		t.Fatalf("decode HTTP fourth activation response: %v", err)
	}
	if activatedFourthResult.ActiveReleaseDigest != releaseFour.ReleaseDigest ||
		activatedFourthResult.Revision != 5 {
		t.Fatalf("HTTP fourth activation=%+v", activatedFourthResult)
	}

	rolledBackHTTP := skillPackageRequest(
		t,
		mux,
		"rollback-three-http",
		"service:integration-publisher",
		"/internal/assistant/skill-package-releases:rollback",
		map[string]any{
			"packageId":        integrationSkillPackageID,
			"expectedRevision": 5,
		},
	)
	if rolledBackHTTP.Code != http.StatusOK {
		t.Fatalf("HTTP rollback status=%d body=%s", rolledBackHTTP.Code, rolledBackHTTP.Body.String())
	}
	var rolledBackHTTPResult model.Activation
	if err := json.Unmarshal(rolledBackHTTP.Body.Bytes(), &rolledBackHTTPResult); err != nil {
		t.Fatalf("decode HTTP rollback response: %v", err)
	}
	if rolledBackHTTPResult.ActiveReleaseDigest != releaseThree.ReleaseDigest ||
		rolledBackHTTPResult.PreviousReleaseDigest != releaseFour.ReleaseDigest ||
		rolledBackHTTPResult.Revision != 6 {
		t.Fatalf("HTTP rollback=%+v", rolledBackHTTPResult)
	}
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_releases",
		bson.M{"packageId": integrationSkillPackageID},
		4,
	)
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_activations",
		bson.M{"packageId": integrationSkillPackageID, "revision": 6},
		1,
	)
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_command_receipts",
		bson.M{"packageId": integrationSkillPackageID},
		10,
	)
	assertSkillPackageDocumentCount(
		t,
		"assistant_skill_package_outbox",
		bson.M{"packageId": integrationSkillPackageID},
		6,
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
		model.AssetCatalog,
		model.AssetActivation,
		model.AssetInput,
		model.AssetInputSchema,
		model.AssetContext,
		model.AssetCapability,
		model.AssetOrchestration,
		model.AssetTrigger,
		model.AssetMemory,
		model.AssetPresentation,
		model.AssetPresentationTemplate,
		model.AssetEvaluation,
		model.AssetPrompt,
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
			{CapabilityID: "context.gathering", Scope: "read_with_consent"},
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

func integrationResourceRelease(
	t *testing.T,
	root string,
	version string,
	privateKey ed25519.PrivateKey,
) model.Release {
	t.Helper()
	memoryAssets := integrationAssetReader{}
	release := integrationRelease(t, memoryAssets, version, privateKey)
	for index := range release.Assets {
		asset := &release.Assets[index]
		content, found := memoryAssets[asset.Locator]
		if !found {
			t.Fatalf("integration asset %q is missing", asset.AssetID)
		}
		relative := filepath.ToSlash(filepath.Join(
			"releases",
			version,
			"assets",
			asset.Kind+".bin",
		))
		path := filepath.Join(root, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("create immutable package asset directory: %v", err)
		}
		if err := os.WriteFile(path, content, 0o600); err != nil {
			t.Fatalf("write immutable package asset %q: %v", asset.AssetID, err)
		}
		asset.Locator = "skill-package://official/" + relative
	}
	release.ReleaseDigest = "sha256:" + strings.Repeat("0", sha256.Size*2)
	release.Signature.Value = "pending"
	digest, err := model.Digest(release)
	if err != nil {
		t.Fatalf("digest immutable resource release: %v", err)
	}
	release.ReleaseDigest = digest
	release.Signature.Value = base64.StdEncoding.EncodeToString(
		ed25519.Sign(privateKey, []byte(digest)),
	)
	return release
}

func skillPackageRequest(
	t *testing.T,
	handler http.Handler,
	commandID string,
	publisherID string,
	path string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal SkillPackageRelease request: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{Subject: publisherID}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
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
