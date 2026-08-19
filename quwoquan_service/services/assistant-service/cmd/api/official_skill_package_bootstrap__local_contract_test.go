// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
package bootstrap

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	packageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
)

const bootstrapTestKeyID = "official-bootstrap-local-contract"

type bootstrapMemoryStore struct {
	releases    map[string]packagemodel.Release
	stageCmds   map[string]string
	activation  packagemodel.Activation
	commandRcps map[string]packagemodel.Activation
	stageWrites int
	commits     int
}

func newBootstrapMemoryStore() *bootstrapMemoryStore {
	return &bootstrapMemoryStore{
		releases:    map[string]packagemodel.Release{},
		stageCmds:   map[string]string{},
		commandRcps: map[string]packagemodel.Activation{},
	}
}

func (store *bootstrapMemoryStore) GetRelease(
	_ context.Context,
	packageID string,
	releaseDigest string,
) (packagemodel.Release, bool, error) {
	release, found := store.releases[packageID+"\x00"+releaseDigest]
	return release, found, nil
}

func (store *bootstrapMemoryStore) Stage(
	_ context.Context,
	commandID string,
	commandDigest string,
	release packagemodel.Release,
) (packagemodel.Release, bool, error) {
	if previous, found := store.stageCmds[commandID]; found {
		if previous != commandDigest {
			return packagemodel.Release{}, false, packagemodel.ErrInvalidRelease
		}
		return store.releases[release.PackageID+"\x00"+release.ReleaseDigest], true, nil
	}
	store.releases[release.PackageID+"\x00"+release.ReleaseDigest] = release
	store.stageCmds[commandID] = commandDigest
	store.stageWrites++
	return release, false, nil
}

func (store *bootstrapMemoryStore) GetActivation(
	_ context.Context,
	packageID string,
) (packagemodel.Activation, bool, error) {
	found := store.activation.PackageID == packageID &&
		store.activation.ActiveReleaseDigest != ""
	return store.activation, found, nil
}

func (store *bootstrapMemoryStore) GetCommandResult(
	_ context.Context,
	commandID string,
	_ string,
	_ string,
) (packagemodel.Activation, bool, error) {
	activation, found := store.commandRcps[commandID]
	return activation, found, nil
}

func (store *bootstrapMemoryStore) CommitActivation(
	_ context.Context,
	commandID string,
	_ string,
	expectedRevision int,
	next packagemodel.Activation,
	_ string,
) (packagemodel.Activation, bool, error) {
	if activation, found := store.commandRcps[commandID]; found {
		return activation, true, nil
	}
	if store.activation.Revision != expectedRevision {
		return packagemodel.Activation{}, false, packagemodel.ErrRevisionConflict
	}
	store.activation = next
	store.commandRcps[commandID] = next
	store.commits++
	return next, false, nil
}

// writeSignedPublication 用真实源资产编译并签名一个官方包,按
// skill-package-build 的 writePackage 布局写入 assetRoot,返回信任公钥。
func writeSignedPublication(
	t *testing.T,
	assetRoot string,
	buildID string,
	keyID string,
) ed25519.PublicKey {
	t.Helper()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	sourceRoot := filepath.Join("..", "..", "resources", "skill_packages", "official")
	bundle, err := resourcebuilder.NewSourceBuilderAt(sourceRoot).Compile(t.Context())
	if err != nil {
		t.Fatalf("compile official Skill source: %v", err)
	}
	builtAt := time.Date(2026, time.August, 13, 12, 0, 0, 0, time.UTC)
	built, err := resourcebuilder.BuildPackage(bundle, resourcebuilder.PackageBuildOptions{
		PackageID:        "assistant.session.skills",
		PackageVersion:   "1.0.0",
		BuildID:          buildID,
		SourceRepository: "quwoquan",
		SourceRevision:   strings.Repeat("a", 40),
		BuiltAt:          builtAt,
		RuntimeCompatibility: packagemodel.RuntimeCompatibility{
			APIVersion:            packagemodel.RuntimeAPIVersion,
			MinimumRuntimeVersion: packagemodel.RuntimeVersion,
			MaximumRuntimeVersion: packagemodel.RuntimeVersion,
		},
		CapabilityGrants: []packagemodel.CapabilityGrant{{
			CapabilityID: "assistant.skill",
			Scope:        "official",
		}},
		SigningKeyID:      keyID,
		SigningPrivateKey: privateKey,
	})
	if err != nil {
		t.Fatalf("build official Skill package: %v", err)
	}
	prefix := "releases/" + buildID + "/"
	for _, file := range built.Files {
		relative := strings.TrimPrefix(file.RelativePath, prefix)
		path := filepath.Join(assetRoot, "releases", buildID, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, file.Content, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	receipt, err := packagemodel.PassedEvaluationReceiptFor(built.Release, builtAt)
	if err != nil {
		t.Fatalf("build evaluation receipt: %v", err)
	}
	publication := packageartifact.PublicationArtifact{
		CommandID:         "official-bootstrap-" + buildID,
		ExpectedRevision:  0,
		ActivatedBy:       "service:local-contract-bootstrap",
		Release:           built.Release,
		EvaluationReceipt: receipt,
	}
	payload, err := json.MarshalIndent(publication, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		filepath.Join(assetRoot, "releases", buildID, "publication.json"),
		append(payload, '\n'),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	return publicKey
}

func newBootstrapService(
	t *testing.T,
	store *bootstrapMemoryStore,
	assetRoot string,
	trusted map[string]ed25519.PublicKey,
) *packageapplication.Service {
	t.Helper()
	assets, err := packageartifact.NewResourceReader(assetRoot)
	if err != nil {
		t.Fatal(err)
	}
	return packageapplication.NewService(
		store,
		store,
		assets,
		packageapplication.NewEd25519Verifier(trusted),
		packageapplication.RuntimeIdentity{
			APIVersion: packagemodel.RuntimeAPIVersion,
			Version:    packagemodel.RuntimeVersion,
		},
		func() time.Time {
			return time.Date(2026, time.August, 13, 12, 30, 0, 0, time.UTC)
		},
	)
}

func TestOfficialSkillPackageBootstrapActivatesOnceOnEmptyStoreAndIsIdempotent(
	t *testing.T,
) {
	t.Parallel()
	assetRoot := t.TempDir()
	publicKey := writeSignedPublication(t, assetRoot, "bootstrap-a", bootstrapTestKeyID)
	store := newBootstrapMemoryStore()
	service := newBootstrapService(t, store, assetRoot, map[string]ed25519.PublicKey{
		bootstrapTestKeyID: publicKey,
	})

	if err := bootstrapOfficialSkillPackage(
		t.Context(), service, store, assetRoot,
	); err != nil {
		t.Fatalf("bootstrap on empty store: %v", err)
	}
	if store.activation.ActiveReleaseDigest == "" ||
		store.activation.PackageID != "assistant.session.skills" {
		t.Fatalf("official package was not activated: %#v", store.activation)
	}
	firstDigest := store.activation.ActiveReleaseDigest
	stageWrites, commits := store.stageWrites, store.commits

	// 第二次自举必须零写入:激活指针与写计数保持不变。
	if err := bootstrapOfficialSkillPackage(
		t.Context(), service, store, assetRoot,
	); err != nil {
		t.Fatalf("bootstrap replay: %v", err)
	}
	if store.activation.ActiveReleaseDigest != firstDigest ||
		store.stageWrites != stageWrites || store.commits != commits {
		t.Fatalf(
			"bootstrap replay mutated state: digest=%s writes=%d commits=%d",
			store.activation.ActiveReleaseDigest, store.stageWrites, store.commits,
		)
	}
}

func TestOfficialSkillPackageBootstrapConvergesStaleActivationToPublication(
	t *testing.T,
) {
	t.Parallel()
	assetRoot := t.TempDir()
	publicKey := writeSignedPublication(t, assetRoot, "bootstrap-b", bootstrapTestKeyID)
	store := newBootstrapMemoryStore()
	// 既有激活指向旧 candidate 的 release(其资产已随旧 candidate 退役);
	// 自举必须以当前指针 revision 做 CAS,把激活受控收敛到挂载 publication。
	store.activation = packagemodel.Activation{
		PackageID:           "assistant.session.skills",
		ActiveReleaseDigest: "sha256:" + strings.Repeat("c", 64),
		Revision:            7,
	}
	service := newBootstrapService(t, store, assetRoot, map[string]ed25519.PublicKey{
		bootstrapTestKeyID: publicKey,
	})

	if err := bootstrapOfficialSkillPackage(
		t.Context(), service, store, assetRoot,
	); err != nil {
		t.Fatalf("converge stale activation: %v", err)
	}
	if store.activation.ActiveReleaseDigest == "sha256:"+strings.Repeat("c", 64) {
		t.Fatalf("stale activation was not converged: %#v", store.activation)
	}
	if store.commits != 1 {
		t.Fatalf("converge must commit exactly once: %#v", store)
	}
}

func TestOfficialSkillPackageBootstrapFailsClosedWithoutPublication(t *testing.T) {
	t.Parallel()
	assetRoot := t.TempDir()
	store := newBootstrapMemoryStore()
	service := newBootstrapService(t, store, assetRoot, map[string]ed25519.PublicKey{})

	err := bootstrapOfficialSkillPackage(t.Context(), service, store, assetRoot)
	if err == nil || !strings.Contains(err.Error(), "no publication") {
		t.Fatalf("missing publication must fail closed with guidance, got %v", err)
	}
	if store.stageWrites != 0 || store.commits != 0 {
		t.Fatalf("bootstrap wrote without publication: %#v", store)
	}
}

func TestOfficialSkillPackageBootstrapRejectsAmbiguousPublications(t *testing.T) {
	t.Parallel()
	assetRoot := t.TempDir()
	publicKey := writeSignedPublication(t, assetRoot, "bootstrap-c1", bootstrapTestKeyID)
	_ = writeSignedPublication(t, assetRoot, "bootstrap-c2", bootstrapTestKeyID)
	store := newBootstrapMemoryStore()
	service := newBootstrapService(t, store, assetRoot, map[string]ed25519.PublicKey{
		bootstrapTestKeyID: publicKey,
	})

	err := bootstrapOfficialSkillPackage(t.Context(), service, store, assetRoot)
	if err == nil || !strings.Contains(err.Error(), "exactly one publication") {
		t.Fatalf("ambiguous publications must fail closed, got %v", err)
	}
	if store.stageWrites != 0 || store.commits != 0 {
		t.Fatalf("bootstrap wrote despite ambiguity: %#v", store)
	}
}

func TestOfficialSkillPackageBootstrapUsesBuildBoundCommandIdentity(t *testing.T) {
	t.Parallel()
	assetRoot := t.TempDir()
	publicKey := writeSignedPublication(t, assetRoot, "bootstrap-e", bootstrapTestKeyID)
	store := newBootstrapMemoryStore()
	service := newBootstrapService(t, store, assetRoot, map[string]ed25519.PublicKey{
		bootstrapTestKeyID: publicKey,
	})

	if err := bootstrapOfficialSkillPackage(
		t.Context(), service, store, assetRoot,
	); err != nil {
		t.Fatalf("bootstrap official package: %v", err)
	}
	var releaseDigest string
	for _, release := range store.releases {
		releaseDigest = release.ReleaseDigest
	}
	if releaseDigest == "" {
		t.Fatal("bootstrap did not stage the release")
	}
	wantStage := "official-bootstrap-bootstrap-e:stage"
	if _, found := store.stageCmds[wantStage]; !found {
		t.Fatalf("stage command is not build-bound: %#v", store.stageCmds)
	}
	wantActivate := "official-bootstrap-bootstrap-e:activate"
	if _, found := store.commandRcps[wantActivate]; !found {
		t.Fatalf("activation command is not build-bound: %#v", store.commandRcps)
	}
	if !strings.Contains(wantStage, "bootstrap-e") || releaseDigest == "" {
		t.Fatalf("bootstrap command/release identity is incomplete: %s %s", wantStage, releaseDigest)
	}
}

func TestOfficialSkillPackageBootstrapRejectsUntrustedSignature(t *testing.T) {
	t.Parallel()
	assetRoot := t.TempDir()
	// 用未登记进信任集的 keyID 签名:Stage 必须验签失败,不产生激活。
	writeSignedPublication(t, assetRoot, "bootstrap-d", "untrusted-key")
	otherPublic, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	store := newBootstrapMemoryStore()
	service := newBootstrapService(t, store, assetRoot, map[string]ed25519.PublicKey{
		bootstrapTestKeyID: otherPublic,
	})

	bootstrapErr := bootstrapOfficialSkillPackage(t.Context(), service, store, assetRoot)
	if bootstrapErr == nil ||
		!errors.Is(bootstrapErr, packagemodel.ErrSignatureInvalid) {
		t.Fatalf("untrusted signature must fail closed, got %v", bootstrapErr)
	}
	if store.activation.ActiveReleaseDigest != "" {
		t.Fatalf("untrusted publication was activated: %#v", store.activation)
	}
}
