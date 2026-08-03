// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
package skill_package_release_test

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

const (
	testPackageID = "assistant.session.skills"
	testKeyID     = "assistant-skill-package-test"
)

type releaseReceipt struct {
	digest  string
	release model.Release
}

type memoryRepository struct {
	releases        map[string]model.Release
	releaseReceipts map[string]releaseReceipt
	activation      model.Activation
	receipts        map[string]activationReceipt
	assets          map[string][]byte
	releaseReads    map[string]int
	assetReads      map[string]int
	activeReads     int
}

type activationReceipt struct {
	digest     string
	activation model.Activation
}

func newMemoryRepository() *memoryRepository {
	return &memoryRepository{
		releases:        map[string]model.Release{},
		releaseReceipts: map[string]releaseReceipt{},
		receipts:        map[string]activationReceipt{},
		assets:          map[string][]byte{},
		releaseReads:    map[string]int{},
		assetReads:      map[string]int{},
	}
}

func (repository *memoryRepository) GetRelease(
	_ context.Context,
	packageID string,
	releaseDigest string,
) (model.Release, bool, error) {
	key := packageID + "\x00" + releaseDigest
	repository.releaseReads[key]++
	release, found := repository.releases[key]
	return release, found, nil
}

func (repository *memoryRepository) Stage(
	_ context.Context,
	commandID string,
	commandDigest string,
	release model.Release,
) (model.Release, bool, error) {
	if receipt, found := repository.releaseReceipts[commandID]; found {
		if receipt.digest != commandDigest {
			return model.Release{}, false, model.ErrInvalidRelease
		}
		return receipt.release, true, nil
	}
	key := release.PackageID + "\x00" + release.ReleaseDigest
	if existing, found := repository.releases[key]; found {
		if existing.PackageVersion != release.PackageVersion {
			return model.Release{}, false, model.ErrDigestMismatch
		}
		repository.releaseReceipts[commandID] = releaseReceipt{
			digest: commandDigest, release: existing,
		}
		return existing, true, nil
	}
	repository.releases[key] = release
	repository.releaseReceipts[commandID] = releaseReceipt{
		digest: commandDigest, release: release,
	}
	return release, false, nil
}

func (repository *memoryRepository) ReadAsset(
	_ context.Context,
	locator string,
) ([]byte, error) {
	repository.assetReads[locator]++
	content, found := repository.assets[locator]
	if !found {
		return nil, errors.New("asset not found")
	}
	return append([]byte(nil), content...), nil
}

func (repository *memoryRepository) GetActivation(
	_ context.Context,
	packageID string,
) (model.Activation, bool, error) {
	repository.activeReads++
	return repository.activation,
		repository.activation.PackageID == packageID &&
			repository.activation.ActiveReleaseDigest != "",
		nil
}

func (repository *memoryRepository) GetCommandResult(
	_ context.Context,
	commandID string,
	commandDigest string,
	packageID string,
) (model.Activation, bool, error) {
	receipt, found := repository.receipts[commandID]
	if !found {
		return model.Activation{}, false, nil
	}
	if receipt.digest != commandDigest || receipt.activation.PackageID != packageID {
		return model.Activation{}, false, model.ErrInvalidRelease
	}
	return receipt.activation, true, nil
}

func (repository *memoryRepository) CommitActivation(
	_ context.Context,
	commandID string,
	commandDigest string,
	expectedRevision int,
	next model.Activation,
	_ string,
) (model.Activation, bool, error) {
	if receipt, found := repository.receipts[commandID]; found {
		if receipt.digest != commandDigest {
			return model.Activation{}, false, model.ErrInvalidRelease
		}
		return receipt.activation, true, nil
	}
	if repository.activation.Revision != expectedRevision {
		return model.Activation{}, false, model.ErrRevisionConflict
	}
	repository.activation = next
	repository.receipts[commandID] = activationReceipt{
		digest: commandDigest, activation: next,
	}
	return next, false, nil
}

func TestSkillPackageStageFailsClosedForAssetRuntimeSignatureAndGrant(
	t *testing.T,
) {
	t.Parallel()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 31, 20, 0, 0, 0, time.UTC)
	runtime := application.RuntimeIdentity{
		APIVersion: "assistant-skill/v1",
		Version:    "1.4.0",
	}
	tests := []struct {
		name    string
		mutate  func(*model.Release, *memoryRepository)
		wantErr error
	}{
		{name: "valid"},
		{
			name: "asset tampered",
			mutate: func(release *model.Release, repository *memoryRepository) {
				repository.assets[release.Assets[0].Locator] = []byte("tampered")
			},
			wantErr: model.ErrAssetMismatch,
		},
		{
			name: "runtime incompatible",
			mutate: func(release *model.Release, _ *memoryRepository) {
				release.RuntimeCompatibility.MinimumRuntimeVersion = "2.0.0"
				release.RuntimeCompatibility.MaximumRuntimeVersion = "2.9.9"
				resignRelease(t, release, privateKey)
			},
			wantErr: model.ErrRuntimeMismatch,
		},
		{
			name: "signature untrusted",
			mutate: func(release *model.Release, _ *memoryRepository) {
				release.Signature.KeyID = "other-key"
				resignRelease(t, release, privateKey)
			},
			wantErr: model.ErrSignatureInvalid,
		},
		{
			name: "capability grant malformed",
			mutate: func(release *model.Release, _ *memoryRepository) {
				release.CapabilityGrants[0].CapabilityID = "Tool.Admin"
			},
			wantErr: model.ErrInvalidRelease,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			repository := newMemoryRepository()
			release := signedRelease(t, repository, "1.0.0", privateKey)
			if test.mutate != nil {
				test.mutate(&release, repository)
			}
			service := application.NewService(
				repository,
				repository,
				repository,
				application.NewEd25519Verifier(
					map[string]ed25519.PublicKey{testKeyID: publicKey},
				),
				runtime,
				func() time.Time { return now },
			)
			result, err := service.Stage(
				context.Background(),
				"stage-"+test.name,
				release,
			)
			if test.wantErr != nil {
				if !errors.Is(err, test.wantErr) {
					t.Fatalf("Stage() error = %v, want %v", err, test.wantErr)
				}
				if len(repository.releases) != 0 {
					t.Fatalf("invalid release persisted: %#v", repository.releases)
				}
				return
			}
			if err != nil {
				t.Fatalf("Stage() error = %v", err)
			}
			if result.Release.PackageVersion != "1.0.0" ||
				result.Release.Status != model.StatusStaged ||
				result.Release.ReleaseDigest == "" {
				t.Fatalf("staged release = %#v", result.Release)
			}
		})
	}
}

func TestActiveReleaseUsesDigestCacheAndRollbackReusesVerifiedRelease(
	t *testing.T,
) {
	t.Parallel()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	repository := newMemoryRepository()
	releaseOne := signedRelease(t, repository, "1.0.0", privateKey)
	releaseTwo := signedRelease(t, repository, "1.1.0", privateKey)
	now := time.Date(2026, 7, 31, 21, 0, 0, 0, time.UTC)
	service := application.NewService(
		repository,
		repository,
		repository,
		application.NewEd25519Verifier(
			map[string]ed25519.PublicKey{testKeyID: publicKey},
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
	if _, err := service.Stage(context.Background(), "stage-1", releaseOne); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Stage(context.Background(), "stage-2", releaseTwo); err != nil {
		t.Fatal(err)
	}
	repository.releaseReads = map[string]int{}
	repository.assetReads = map[string]int{}

	firstActivation, err := service.Activate(
		context.Background(),
		"activate-1",
		application.ActivateInput{
			PackageID:        testPackageID,
			ReleaseDigest:    releaseOne.ReleaseDigest,
			ExpectedRevision: 0,
			ActivatedBy:      "service:skill-publisher",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if firstActivation.Activation.Revision != 1 {
		t.Fatalf("first activation = %#v", firstActivation)
	}
	first, err := service.ResolveActive(context.Background(), testPackageID)
	if err != nil {
		t.Fatal(err)
	}
	if err := first.RequireCapabilities([]model.CapabilityGrant{{
		CapabilityID: "tool.web_search",
		Scope:        "read_public",
	}}); err != nil {
		t.Fatalf("declared capability denied: %v", err)
	}
	if err := first.RequireCapabilities([]model.CapabilityGrant{{
		CapabilityID: "tool.admin",
		Scope:        "write",
	}}); !errors.Is(err, model.ErrCapabilityDenied) {
		t.Fatalf("undeclared capability error = %v", err)
	}
	first.Assets[first.Release.Assets[0].AssetID][0] = 'X'
	second, err := service.ResolveActive(context.Background(), testPackageID)
	if err != nil {
		t.Fatal(err)
	}
	if second.Assets[second.Release.Assets[0].AssetID][0] == 'X' {
		t.Fatal("caller mutated digest cache")
	}
	if repository.activeReads != 3 {
		t.Fatalf("active pointer reads = %d, want 3", repository.activeReads)
	}
	assertSingleReleaseRead(t, repository, releaseOne)
	assertSingleAssetRead(t, repository, releaseOne)

	if _, err := service.Activate(
		context.Background(),
		"activate-2",
		application.ActivateInput{
			PackageID:        testPackageID,
			ReleaseDigest:    releaseTwo.ReleaseDigest,
			ExpectedRevision: 1,
			ActivatedBy:      "service:skill-publisher",
		},
	); err != nil {
		t.Fatal(err)
	}
	activeTwo, err := service.ResolveActive(context.Background(), testPackageID)
	if err != nil {
		t.Fatal(err)
	}
	if activeTwo.Release.ReleaseDigest != releaseTwo.ReleaseDigest {
		t.Fatalf("active release = %s", activeTwo.Release.ReleaseDigest)
	}
	assertSingleReleaseRead(t, repository, releaseTwo)
	assertSingleAssetRead(t, repository, releaseTwo)

	rolledBack, err := service.Rollback(
		context.Background(),
		"rollback-1",
		application.RollbackInput{
			PackageID:        testPackageID,
			ExpectedRevision: 2,
			ActivatedBy:      "service:skill-publisher",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if rolledBack.Activation.ActiveReleaseDigest != releaseOne.ReleaseDigest ||
		rolledBack.Activation.PreviousReleaseDigest != releaseTwo.ReleaseDigest ||
		rolledBack.Activation.Revision != 3 {
		t.Fatalf("rollback = %#v", rolledBack)
	}
	activeOneAgain, err := service.ResolveActive(context.Background(), testPackageID)
	if err != nil {
		t.Fatal(err)
	}
	if activeOneAgain.Release.ReleaseDigest != releaseOne.ReleaseDigest {
		t.Fatalf("rolled back active release = %#v", activeOneAgain.Release)
	}
	assertSingleReleaseRead(t, repository, releaseOne)
	assertSingleAssetRead(t, repository, releaseOne)
}

func signedRelease(
	t *testing.T,
	repository *memoryRepository,
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
	assets := make([]model.Asset, 0, len(kinds))
	for _, kind := range kinds {
		locator := fmt.Sprintf("artifact://%s/%s", version, kind)
		content := []byte(version + ":" + kind)
		repository.assets[locator] = content
		sum := sha256.Sum256(content)
		assets = append(assets, model.Asset{
			AssetID:     version + "." + kind,
			Kind:        kind,
			Locator:     locator,
			AssetDigest: "sha256:" + hex.EncodeToString(sum[:]),
		})
	}
	release := model.Release{
		PackageID:      testPackageID,
		PackageVersion: version,
		ReleaseDigest:  "sha256:" + strings.Repeat("0", 64),
		Assets:         assets,
		RuntimeCompatibility: model.RuntimeCompatibility{
			APIVersion:            "assistant-skill/v1",
			MinimumRuntimeVersion: "1.0.0",
			MaximumRuntimeVersion: "1.9.9",
		},
		Provenance: model.Provenance{
			SourceRepository: "https://example.invalid/quwoquan",
			SourceRevision:   "revision-" + version,
			BuildID:          "build-" + version,
			BuiltAt:          time.Date(2026, 7, 31, 19, 0, 0, 0, time.UTC),
		},
		Signature: model.Signature{
			Algorithm: "ed25519",
			KeyID:     testKeyID,
			Value:     "pending",
		},
		CapabilityGrants: []model.CapabilityGrant{
			{CapabilityID: "tool.web_search", Scope: "read_public"},
			{CapabilityID: "context.trip", Scope: "read_with_consent"},
		},
	}
	resignRelease(t, &release, privateKey)
	return release
}

func resignRelease(
	t *testing.T,
	release *model.Release,
	privateKey ed25519.PrivateKey,
) {
	t.Helper()
	release.ReleaseDigest = "sha256:" + strings.Repeat("0", 64)
	release.Signature.Value = "pending"
	digest, err := model.Digest(*release)
	if err != nil {
		t.Fatal(err)
	}
	release.ReleaseDigest = digest
	release.Signature.Value = base64.StdEncoding.EncodeToString(
		ed25519.Sign(privateKey, []byte(digest)),
	)
}

func assertSingleReleaseRead(
	t *testing.T,
	repository *memoryRepository,
	release model.Release,
) {
	t.Helper()
	key := release.PackageID + "\x00" + release.ReleaseDigest
	if repository.releaseReads[key] != 1 {
		t.Fatalf(
			"release %s reads = %d, want 1",
			release.PackageVersion,
			repository.releaseReads[key],
		)
	}
}

func assertSingleAssetRead(
	t *testing.T,
	repository *memoryRepository,
	release model.Release,
) {
	t.Helper()
	for _, asset := range release.Assets {
		if repository.assetReads[asset.Locator] != 1 {
			t.Fatalf(
				"asset %s reads = %d, want 1",
				asset.AssetID,
				repository.assetReads[asset.Locator],
			)
		}
	}
}
