package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

const appIdentityMetadataRelativePath = "_shared/app_artifact_manifest.yaml"

type appIdentityBaseID struct {
	Value      string `yaml:"value"`
	Registered bool   `yaml:"registered"`
}

type appIdentityContract struct {
	DisplayNameBase       string                       `yaml:"display_name_base"`
	BaseApplicationIDs    map[string]appIdentityBaseID `yaml:"base_application_ids"`
	EnvironmentSuffixes   map[string]string            `yaml:"environment_suffixes"`
	EnvironmentMarks      map[string]string            `yaml:"environment_display_marks"`
	BuildModeSuffixes     map[string]string            `yaml:"build_mode_suffixes"`
	BuildModeDisplayMarks map[string]string            `yaml:"build_mode_display_marks"`
}

type appArtifactIdentityMetadata struct {
	SchemaID            string              `yaml:"schema_id"`
	Environments        []string            `yaml:"environments"`
	Platforms           []string            `yaml:"platforms"`
	BuildModes          []string            `yaml:"build_modes"`
	ApplicationIdentity appIdentityContract `yaml:"application_identity"`
}

type generatedAppIdentity struct {
	ApplicationID string `json:"applicationId"`
	DisplayName   string `json:"displayName"`
	Registered    bool   `json:"registered"`
}

type generatedAppIdentityDocument struct {
	Schema       string                                     `json:"schema"`
	Source       string                                     `json:"source"`
	SourceSHA256 string                                     `json:"sourceSha256"`
	Environments []string                                   `json:"environments"`
	BuildModes   []string                                   `json:"buildModes"`
	Identities   map[string]map[string]generatedAppIdentity `json:"identities"`
}

type appIdentityArtifact struct {
	RelativePath string
	Content      []byte
}

type appIdentityGeneratedManifest struct {
	Schema       string                      `json:"schema"`
	Generator    string                      `json:"generator"`
	Source       string                      `json:"source"`
	SourceSHA256 string                      `json:"sourceSha256"`
	Outputs      []appIdentityManifestOutput `json:"outputs"`
}

type appIdentityManifestOutput struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Bytes  int    `json:"bytes"`
}

func runAppIdentityMode(metadataDir, appDir, manifestPath string, check bool) error {
	sourcePath := filepath.Join(metadataDir, filepath.FromSlash(appIdentityMetadataRelativePath))
	sourceBytes, err := os.ReadFile(sourcePath)
	if err != nil {
		return fmt.Errorf("read App identity metadata: %w", err)
	}
	var metadata appArtifactIdentityMetadata
	if err := yaml.Unmarshal(sourceBytes, &metadata); err != nil {
		return fmt.Errorf("decode App identity metadata: %w", err)
	}
	if err := validateAppIdentityMetadata(metadata); err != nil {
		return err
	}
	sourceSum := sha256.Sum256(sourceBytes)
	sourceSHA := hex.EncodeToString(sourceSum[:])
	artifacts, err := renderAppIdentityArtifacts(metadata, sourceSHA)
	if err != nil {
		return err
	}
	if strings.TrimSpace(manifestPath) == "" {
		manifestPath = filepath.Join(appDir, "tool", "app_identity_codegen", "generated_manifest.json")
	}
	manifest := buildAppIdentityGeneratedManifest(artifacts, sourceSHA)
	if check {
		return checkAppIdentityArtifacts(appDir, manifestPath, artifacts, manifest)
	}
	return writeAppIdentityArtifacts(appDir, manifestPath, artifacts, manifest)
}

func validateAppIdentityMetadata(metadata appArtifactIdentityMetadata) error {
	if metadata.SchemaID != "app_artifact_manifest" {
		return fmt.Errorf("App identity metadata schema_id mismatch")
	}
	if len(metadata.Environments) == 0 || len(metadata.BuildModes) == 0 {
		return fmt.Errorf("App identity metadata environment/build-mode matrix is empty")
	}
	contract := metadata.ApplicationIdentity
	if strings.TrimSpace(contract.DisplayNameBase) == "" {
		return fmt.Errorf("application_identity.display_name_base is empty")
	}
	for _, platform := range []string{"android", "ios"} {
		base, ok := contract.BaseApplicationIDs[platform]
		if !ok || strings.TrimSpace(base.Value) == "" {
			return fmt.Errorf("application_identity base ID is missing for %s", platform)
		}
	}
	seen := map[string]string{}
	for _, environment := range metadata.Environments {
		if _, ok := contract.EnvironmentSuffixes[environment]; !ok {
			return fmt.Errorf("application_identity environment suffix is missing for %s", environment)
		}
		if _, ok := contract.EnvironmentMarks[environment]; !ok {
			return fmt.Errorf("application_identity environment display mark is missing for %s", environment)
		}
		for _, buildMode := range metadata.BuildModes {
			if _, ok := contract.BuildModeSuffixes[buildMode]; !ok {
				return fmt.Errorf("application_identity build-mode suffix is missing for %s", buildMode)
			}
			if _, ok := contract.BuildModeDisplayMarks[buildMode]; !ok {
				return fmt.Errorf("application_identity build-mode display mark is missing for %s", buildMode)
			}
			for _, platform := range []string{"android", "ios"} {
				identity := contract.BaseApplicationIDs[platform].Value + contract.EnvironmentSuffixes[environment] + contract.BuildModeSuffixes[buildMode]
				key := platform + ":" + identity
				if previous, exists := seen[key]; exists {
					return fmt.Errorf("App identity collision: %s and %s", previous, environment+"/"+buildMode)
				}
				seen[key] = environment + "/" + buildMode
			}
		}
	}
	return nil
}

func renderAppIdentityArtifacts(metadata appArtifactIdentityMetadata, sourceSHA string) ([]appIdentityArtifact, error) {
	contract := metadata.ApplicationIdentity
	identities := map[string]map[string]generatedAppIdentity{}
	for _, platform := range []string{"android", "ios"} {
		identities[platform] = map[string]generatedAppIdentity{}
		base := contract.BaseApplicationIDs[platform]
		for _, environment := range metadata.Environments {
			for _, buildMode := range metadata.BuildModes {
				identities[platform][environment+"/"+buildMode] = generatedAppIdentity{
					ApplicationID: base.Value + contract.EnvironmentSuffixes[environment] + contract.BuildModeSuffixes[buildMode],
					DisplayName:   contract.DisplayNameBase + contract.EnvironmentMarks[environment] + contract.BuildModeDisplayMarks[buildMode],
					Registered:    base.Registered,
				}
			}
		}
	}
	document := generatedAppIdentityDocument{
		Schema:       "qwq.app-identity-generated",
		Source:       appIdentityMetadataRelativePath,
		SourceSHA256: "sha256:" + sourceSHA,
		Environments: append([]string(nil), metadata.Environments...),
		BuildModes:   append([]string(nil), metadata.BuildModes...),
		Identities:   identities,
	}
	jsonBytes, err := json.MarshalIndent(document, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("encode generated App identity JSON: %w", err)
	}
	artifacts := []appIdentityArtifact{{
		RelativePath: "android/app/app_identity.generated.json",
		Content:      append(jsonBytes, '\n'),
	}}
	for _, environment := range metadata.Environments {
		identityLines := []string{
			"// Generated from " + appIdentityMetadataRelativePath + "; do not edit.",
			"QWQ_APP_IDENTITY_SOURCE_SHA256 = sha256:" + sourceSHA,
			"QWQ_APP_RUNTIME_ENV = " + environment,
			"QWQ_IOS_BASE_BUNDLE_ID = " + contract.BaseApplicationIDs["ios"].Value,
			"QWQ_ENV_BUNDLE_ID_SUFFIX = " + contract.EnvironmentSuffixes[environment],
			"QWQ_APP_DISPLAY_NAME_BASE = " + contract.DisplayNameBase,
			"QWQ_ENV_DISPLAY_MARK = " + contract.EnvironmentMarks[environment],
			"",
		}
		artifacts = append(artifacts, appIdentityArtifact{
			RelativePath: filepath.ToSlash(filepath.Join("ios", "Flutter", "Identity", environment+".xcconfig")),
			Content:      []byte(strings.Join(identityLines, "\n")),
		})
		for _, buildMode := range metadata.BuildModes {
			configurationName := strings.ToUpper(buildMode[:1]) + buildMode[1:] + "-" + environment
			baseConfigName := "Base/" + strings.ToUpper(buildMode[:1]) + buildMode[1:] + ".xcconfig"
			lowerConfigurationName := strings.ToLower(configurationName)
			wrapper := strings.Join([]string{
				"// Generated from " + appIdentityMetadataRelativePath + "; do not edit.",
				"#include \"" + baseConfigName + "\"",
				"#include? \"Pods/Target Support Files/Pods-Runner/Pods-Runner." + lowerConfigurationName + ".xcconfig\"",
				"#include \"Identity/" + environment + ".xcconfig\"",
				"QWQ_EXPECTED_BUILD_MODE = " + buildMode,
				"QWQ_EXPECTED_CONFIGURATION = " + configurationName,
				"QWQ_MODE_BUNDLE_ID_SUFFIX = " + contract.BuildModeSuffixes[buildMode],
				"QWQ_MODE_DISPLAY_MARK = " + contract.BuildModeDisplayMarks[buildMode],
				"QWQ_BUNDLE_ID_SUFFIX = $(QWQ_ENV_BUNDLE_ID_SUFFIX)$(QWQ_MODE_BUNDLE_ID_SUFFIX)",
				"QWQ_APP_DISPLAY_NAME = $(QWQ_APP_DISPLAY_NAME_BASE)$(QWQ_ENV_DISPLAY_MARK)$(QWQ_MODE_DISPLAY_MARK)",
				"FLUTTER_TARGET = lib/main_prod.dart",
				"",
			}, "\n")
			artifacts = append(artifacts, appIdentityArtifact{
				RelativePath: filepath.ToSlash(filepath.Join("ios", "Flutter", configurationName+".xcconfig")),
				Content:      []byte(wrapper),
			})
		}
	}
	return artifacts, nil
}

func buildAppIdentityGeneratedManifest(artifacts []appIdentityArtifact, sourceSHA string) appIdentityGeneratedManifest {
	outputs := make([]appIdentityManifestOutput, 0, len(artifacts))
	for _, artifact := range artifacts {
		sum := sha256.Sum256(artifact.Content)
		outputs = append(outputs, appIdentityManifestOutput{
			Path:   artifact.RelativePath,
			SHA256: "sha256:" + hex.EncodeToString(sum[:]),
			Bytes:  len(artifact.Content),
		})
	}
	sort.Slice(outputs, func(i, j int) bool { return outputs[i].Path < outputs[j].Path })
	return appIdentityGeneratedManifest{
		Schema:       "qwq.app-identity-codegen-manifest",
		Generator:    "tools/codegen_app_metadata --app-identity-only",
		Source:       appIdentityMetadataRelativePath,
		SourceSHA256: "sha256:" + sourceSHA,
		Outputs:      outputs,
	}
}

func writeAppIdentityArtifacts(appDir, manifestPath string, artifacts []appIdentityArtifact, manifest appIdentityGeneratedManifest) error {
	for _, artifact := range artifacts {
		path := filepath.Join(appDir, filepath.FromSlash(artifact.RelativePath))
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			return fmt.Errorf("create generated App identity directory: %w", err)
		}
		if err := os.WriteFile(path, artifact.Content, 0644); err != nil {
			return fmt.Errorf("write generated App identity artifact %s: %w", path, err)
		}
		fmt.Printf("generated: %s\n", path)
	}
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return fmt.Errorf("encode App identity generated manifest: %w", err)
	}
	data = append(data, '\n')
	if err := os.MkdirAll(filepath.Dir(manifestPath), 0755); err != nil {
		return fmt.Errorf("create App identity manifest directory: %w", err)
	}
	if err := os.WriteFile(manifestPath, data, 0644); err != nil {
		return fmt.Errorf("write App identity generated manifest: %w", err)
	}
	fmt.Printf("generated manifest: %s\n", manifestPath)
	return nil
}

func checkAppIdentityArtifacts(appDir, manifestPath string, artifacts []appIdentityArtifact, manifest appIdentityGeneratedManifest) error {
	for _, artifact := range artifacts {
		path := filepath.Join(appDir, filepath.FromSlash(artifact.RelativePath))
		actual, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("generated App identity artifact is missing: %s", path)
		}
		if string(actual) != string(artifact.Content) {
			return fmt.Errorf("generated App identity artifact is stale: %s", path)
		}
	}
	expected, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return fmt.Errorf("encode expected App identity manifest: %w", err)
	}
	expected = append(expected, '\n')
	actual, err := os.ReadFile(manifestPath)
	if err != nil {
		return fmt.Errorf("App identity generated manifest is missing: %s", manifestPath)
	}
	if string(actual) != string(expected) {
		return fmt.Errorf("App identity generated manifest is stale: %s", manifestPath)
	}
	fmt.Printf("verified App identity artifacts: %d\n", len(artifacts))
	return nil
}
