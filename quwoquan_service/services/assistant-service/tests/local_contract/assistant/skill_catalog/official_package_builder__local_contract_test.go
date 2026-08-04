// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package local_contract

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
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

func TestOfficialPackageBuilderEmitsIndividuallyAddressedSignedAssets(
	t *testing.T,
) {
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile official Skill source: %v", err)
	}
	assertCanonicalOfficialSkillSourceRoot(t, bundle.Root)
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate signing key: %v", err)
	}
	built, err := resourcebuilder.BuildPackage(
		bundle,
		resourcebuilder.PackageBuildOptions{
			PackageID:        "assistant.session.skills",
			PackageVersion:   "1.0.0",
			BuildID:          "local-contract-build",
			SourceRepository: "quwoquan",
			SourceRevision:   strings.Repeat("a", 40),
			BuiltAt:          time.Date(2026, 8, 2, 6, 0, 0, 0, time.UTC),
			RuntimeCompatibility: packagemodel.RuntimeCompatibility{
				APIVersion:            packagemodel.RuntimeAPIVersion,
				MinimumRuntimeVersion: "1.0.0",
				MaximumRuntimeVersion: "1.0.0",
			},
			CapabilityGrants: []packagemodel.CapabilityGrant{{
				CapabilityID: "assistant.skill",
				Scope:        "official",
			}},
			SigningKeyID:      "local-contract-key",
			SigningPrivateKey: privateKey,
		},
	)
	if err != nil {
		t.Fatalf("build official Skill package: %v", err)
	}
	assertRoutingFallbackReplayDigestComesFromCanonicalSource(t, bundle)
	assertCanonicalPackageDigests(t, built)
	publication := packageartifact.PublicationArtifact{
		CommandID:        "local-contract-publication",
		ExpectedRevision: 0,
		ActivatedBy:      "local-contract-operator",
		Release:          built.Release,
	}
	if err := publication.Validate(); err != nil {
		t.Fatalf("publisher rejected canonical built package: %v", err)
	}
	if len(built.Files) != len(built.Release.Assets) || len(built.Files) < 20 {
		t.Fatalf("built files=%d assets=%d", len(built.Files), len(built.Release.Assets))
	}
	foundPresentationTemplate := false
	for _, asset := range built.Release.Assets {
		if asset.Kind == packagemodel.AssetPresentationTemplate &&
			asset.AssetID == "presentation_template:travel_companion:travel.route_map" {
			foundPresentationTemplate = true
			break
		}
	}
	if !foundPresentationTemplate {
		t.Fatalf("built package misses travel.route_map presentation template")
	}
	if err := packageapplication.NewEd25519Verifier(
		map[string]ed25519.PublicKey{"local-contract-key": publicKey},
	).Verify(context.Background(), built.Release); err != nil {
		t.Fatalf("verify built release signature: %v", err)
	}
	staged, err := packagemodel.Stage(built.Release, time.Now())
	if err != nil || staged.ReleaseDigest != built.Release.ReleaseDigest {
		t.Fatalf("stage built release=%+v err=%v", staged, err)
	}
	root := t.TempDir()
	for _, file := range built.Files {
		path := filepath.Join(root, filepath.FromSlash(file.RelativePath))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("mkdir package asset: %v", err)
		}
		if err := os.WriteFile(path, file.Content, 0o644); err != nil {
			t.Fatalf("write package asset: %v", err)
		}
	}
	reader, err := packageartifact.NewResourceReader(root)
	if err != nil {
		t.Fatalf("create bounded package reader: %v", err)
	}
	for _, asset := range built.Release.Assets {
		if _, err := reader.ReadAsset(t.Context(), asset.Locator); err != nil {
			t.Fatalf("read built asset %q: %v", asset.AssetID, err)
		}
	}
}

func assertCanonicalOfficialSkillSourceRoot(t *testing.T, actual string) {
	t.Helper()
	serviceRoot := assistantServiceRoot(t)
	expected := filepath.Join(serviceRoot, "resources", "skill_packages", "official")
	if filepath.Clean(actual) != filepath.Clean(expected) {
		t.Fatalf("official Skill source root=%q, want %q", actual, expected)
	}
	info, err := os.Lstat(expected)
	if err != nil {
		t.Fatalf("stat canonical official Skill source root: %v", err)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		t.Fatalf("canonical official Skill source root must not be a symlink: %s", expected)
	}
	legacy := filepath.Join(
		serviceRoot,
		"resources",
		"skills",
		"assistant",
		"assistant_session",
	)
	if _, err := os.Lstat(legacy); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("retired official Skill source root still exists: %s (err=%v)", legacy, err)
	}
}

func assertRoutingFallbackReplayDigestComesFromCanonicalSource(
	t *testing.T,
	bundle resourcebuilder.SourceBundle,
) {
	t.Helper()
	var fallbackFound bool
	for _, manifest := range bundle.ResolvedManifests {
		if !manifest.RoutingFallback {
			continue
		}
		if fallbackFound {
			t.Fatal("official Skill source contains multiple routing fallbacks")
		}
		fallbackFound = true
		profileDigest, err := manifest.ResolvedProfileDigest()
		if err != nil {
			t.Fatalf("resolve routing fallback profile digest: %v", err)
		}
		replay, _, err := bundle.ReplayCorpus.ResolveAsset(
			manifest.ReplayAssetRef,
			manifest.SkillID,
		)
		if err != nil {
			t.Fatalf("resolve routing fallback replay asset: %v", err)
		}
		if replay.SkillProfileDigest != profileDigest {
			t.Fatalf(
				"routing fallback replay digest=%q, canonical profile digest=%q",
				replay.SkillProfileDigest,
				profileDigest,
			)
		}
		t.Logf(
			"canonical routing fallback skill=%s profileDigest=%s",
			manifest.SkillID,
			profileDigest,
		)
	}
	if !fallbackFound {
		t.Fatal("official Skill source has no routing fallback")
	}
}

func assertCanonicalPackageDigests(
	t *testing.T,
	built resourcebuilder.BuiltPackage,
) {
	t.Helper()
	files := make(map[string][]byte, len(built.Files))
	for _, file := range built.Files {
		files[file.RelativePath] = file.Content
	}
	for _, asset := range built.Release.Assets {
		const locatorPrefix = "skill-package://official/"
		path := strings.TrimPrefix(asset.Locator, locatorPrefix)
		if path == asset.Locator {
			t.Fatalf("asset %q has non-canonical locator %q", asset.AssetID, asset.Locator)
		}
		content, found := files[path]
		if !found {
			t.Fatalf("asset %q has no built file %q", asset.AssetID, path)
		}
		sum := sha256.Sum256(content)
		actual := "sha256:" + hex.EncodeToString(sum[:])
		if asset.AssetDigest != actual {
			t.Fatalf(
				"asset %q digest=%q, canonical bytes digest=%q",
				asset.AssetID,
				asset.AssetDigest,
				actual,
			)
		}
	}
	releaseDigest, err := packagemodel.Digest(built.Release)
	if err != nil {
		t.Fatalf("recompute canonical Skill package release digest: %v", err)
	}
	if built.Release.ReleaseDigest != releaseDigest {
		t.Fatalf(
			"built release digest=%q, canonical digest=%q",
			built.Release.ReleaseDigest,
			releaseDigest,
		)
	}
	t.Logf("canonical Skill package releaseDigest=%s", releaseDigest)
}
