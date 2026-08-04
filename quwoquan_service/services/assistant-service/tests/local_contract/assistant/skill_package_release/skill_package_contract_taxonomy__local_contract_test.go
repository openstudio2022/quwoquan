// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package skill_package_release_test

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"sort"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	skill "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

func TestCanonicalSkillManifestFieldsMatchGoManifest(t *testing.T) {
	var schema struct {
		Fields []struct {
			Name string `yaml:"name"`
		} `yaml:"fields"`
	}
	readAssistantContractYAML(
		t,
		"contracts/_shared/assistant_skill_manifest/schema.yaml",
		&schema,
	)

	canonicalFields := make([]string, 0, len(schema.Fields))
	for _, field := range schema.Fields {
		canonicalFields = append(canonicalFields, strings.TrimSpace(field.Name))
	}
	sort.Strings(canonicalFields)

	manifestType := reflect.TypeOf(skill.Manifest{})
	goFields := make([]string, 0, manifestType.NumField())
	for index := 0; index < manifestType.NumField(); index++ {
		jsonName := strings.Split(manifestType.Field(index).Tag.Get("json"), ",")[0]
		if jsonName == "" || jsonName == "-" {
			continue
		}
		goFields = append(goFields, jsonName)
	}
	sort.Strings(goFields)

	if !reflect.DeepEqual(canonicalFields, goFields) {
		t.Fatalf(
			"canonical SkillManifest fields=%v, Go JSON fields=%v",
			canonicalFields,
			goFields,
		)
	}
}

func TestCanonicalSkillPackageAssetKindsMatchRequiredReleaseKinds(t *testing.T) {
	var fields struct {
		Enums map[string]struct {
			Values []string `yaml:"values"`
		} `yaml:"enums"`
	}
	readAssistantContractYAML(
		t,
		"contracts/assistant/skill_package_release/fields.yaml",
		&fields,
	)
	canonicalKinds := fields.Enums["SkillPackageAssetKind"].Values
	if len(canonicalKinds) == 0 {
		t.Fatal("canonical SkillPackageAssetKind is empty")
	}

	release := validReleaseWithKinds(canonicalKinds)
	if _, err := model.Normalize(release); err != nil {
		t.Fatalf(
			"canonical SkillPackageAssetKind does not match release domain: %v",
			err,
		)
	}
	for omitted := range canonicalKinds {
		assets := append([]model.Asset(nil), release.Assets[:omitted]...)
		assets = append(assets, release.Assets[omitted+1:]...)
		candidate := release
		candidate.Assets = assets
		if _, err := model.Normalize(candidate); err == nil {
			t.Fatalf(
				"canonical asset kind %q is not required by release domain",
				canonicalKinds[omitted],
			)
		}
	}
}

func validReleaseWithKinds(kinds []string) model.Release {
	assets := make([]model.Asset, 0, len(kinds))
	for _, kind := range kinds {
		assets = append(assets, model.Asset{
			AssetID:     "asset-" + kind,
			Kind:        kind,
			Locator:     "skill-package://official/test/asset-" + kind,
			AssetDigest: "sha256:" + strings.Repeat("0", 64),
		})
	}
	return model.Release{
		PackageID:      "assistant.session.skills",
		PackageVersion: "1.0.0",
		ReleaseDigest:  "sha256:" + strings.Repeat("0", 64),
		Assets:         assets,
		RuntimeCompatibility: model.RuntimeCompatibility{
			APIVersion:            model.RuntimeAPIVersion,
			MinimumRuntimeVersion: model.RuntimeVersion,
			MaximumRuntimeVersion: model.RuntimeVersion,
		},
		Provenance: model.Provenance{
			SourceRepository: "https://example.invalid/quwoquan",
			SourceRevision:   "revision",
			BuildID:          "build",
			BuiltAt:          time.Date(2026, 8, 3, 0, 0, 0, 0, time.UTC),
		},
		Signature: model.Signature{
			Algorithm: "ed25519",
			KeyID:     "test-key",
			Value:     "test-signature",
		},
		CapabilityGrants: []model.CapabilityGrant{
			{CapabilityID: "tool.web_search", Scope: "read_public"},
		},
	}
}

func readAssistantContractYAML(t *testing.T, relativePath string, target any) {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(
		filepath.Dir(file), "..", "..", "..", "..",
	))
	payload, err := os.ReadFile(filepath.Join(serviceRoot, filepath.FromSlash(relativePath)))
	if err != nil {
		t.Fatalf("read %s: %v", relativePath, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("decode %s: %v", relativePath, err)
	}
}
