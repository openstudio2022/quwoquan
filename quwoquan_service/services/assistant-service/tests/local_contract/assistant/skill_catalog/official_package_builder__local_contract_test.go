// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package local_contract

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
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
