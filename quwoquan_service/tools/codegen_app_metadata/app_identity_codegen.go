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
	BuildProfileSuffixes  map[string]string            `yaml:"build_profile_suffixes"`
	BuildProfileMarks     map[string]string            `yaml:"build_profile_display_marks"`
	BuildModeSuffixes     map[string]string            `yaml:"build_mode_suffixes"`
	BuildModeDisplayMarks map[string]string            `yaml:"build_mode_display_marks"`
}

type appBuildProfileContract struct {
	Environments []string `yaml:"environments"`
	LaunchPolicy string   `yaml:"launch_policy"`
}

type appArtifactIdentityMetadata struct {
	SchemaID            string                             `yaml:"schema_id"`
	Environments        []string                           `yaml:"environments"`
	Platforms           []string                           `yaml:"platforms"`
	BuildModes          []string                           `yaml:"build_modes"`
	BuildProfiles       map[string]appBuildProfileContract `yaml:"build_profiles"`
	ApplicationIdentity appIdentityContract                `yaml:"application_identity"`
}

type generatedAppIdentity struct {
	ApplicationID string `json:"applicationId"`
	DisplayName   string `json:"displayName"`
	Registered    bool   `json:"registered"`
	BuildProfile  string `json:"buildProfile"`
	BuildMode     string `json:"buildMode"`
	Environment   string `json:"environment,omitempty"`
	Promotable    bool   `json:"promotable"`
}

type generatedAppIdentityDocument struct {
	Schema              string                                     `json:"schema"`
	Source              string                                     `json:"source"`
	SourceSHA256        string                                     `json:"sourceSha256"`
	Environments        []string                                   `json:"environments"`
	BuildProfiles       []string                                   `json:"buildProfiles"`
	EnvironmentProfiles map[string]string                          `json:"environmentProfiles"`
	BuildModes          []string                                   `json:"buildModes"`
	IdentityTargets     []string                                   `json:"identityTargets"`
	Identities          map[string]map[string]generatedAppIdentity `json:"identities"`
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

func validateExactKeys(label string, actual map[string]string, expected []string) error {
	if len(actual) != len(expected) {
		return fmt.Errorf("%s keys must equal %s", label, strings.Join(expected, ","))
	}
	for _, key := range expected {
		if _, ok := actual[key]; !ok {
			return fmt.Errorf("%s is missing %s", label, key)
		}
	}
	return nil
}

func validateRequiredKeys(label string, actual map[string]string, required []string) error {
	for _, key := range required {
		if _, ok := actual[key]; !ok {
			return fmt.Errorf("%s is missing %s", label, key)
		}
	}
	return nil
}

func validateAppIdentityMetadata(metadata appArtifactIdentityMetadata) error {
	if metadata.SchemaID != "app_artifact_manifest" {
		return fmt.Errorf("App identity metadata schema_id mismatch")
	}
	if len(metadata.Environments) == 0 || len(metadata.BuildProfiles) == 0 || len(metadata.BuildModes) == 0 {
		return fmt.Errorf("App identity metadata environment/build-profile/build-mode matrix is empty")
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
	profiles, environmentProfiles, err := resolveBuildProfiles(metadata)
	if err != nil {
		return err
	}
	if len(environmentProfiles) != len(metadata.Environments) {
		return fmt.Errorf("build_profiles must own every canonical environment exactly once")
	}
	if err := validateExactKeys("application_identity.build_profile_suffixes", contract.BuildProfileSuffixes, profiles); err != nil {
		return err
	}
	if err := validateExactKeys("application_identity.build_profile_display_marks", contract.BuildProfileMarks, profiles); err != nil {
		return err
	}
	developmentEnvironments := metadata.BuildProfiles["nonprod"].Environments
	developmentModes := []string{"debug", "profile"}
	if err := validateRequiredKeys("application_identity.build_mode_suffixes", contract.BuildModeSuffixes, developmentModes); err != nil {
		return err
	}
	if err := validateRequiredKeys("application_identity.build_mode_display_marks", contract.BuildModeDisplayMarks, developmentModes); err != nil {
		return err
	}
	seen := map[string]string{}
	for _, platform := range []string{"android", "ios"} {
		base := contract.BaseApplicationIDs[platform].Value
		for _, profile := range profiles {
			id := base + contract.BuildProfileSuffixes[profile]
			if previous, ok := seen[platform+":"+id]; ok {
				return fmt.Errorf("App identity collision: %s and %s/release", previous, profile)
			}
			seen[platform+":"+id] = profile + "/release"
		}
		for _, environment := range developmentEnvironments {
			for _, mode := range developmentModes {
				id := base + "." + environment + contract.BuildModeSuffixes[mode]
				if previous, ok := seen[platform+":"+id]; ok {
					return fmt.Errorf("App identity collision: %s and %s/%s", previous, environment, mode)
				}
				seen[platform+":"+id] = environment + "/" + mode
			}
		}
	}
	return nil
}

func resolveBuildProfiles(metadata appArtifactIdentityMetadata) ([]string, map[string]string, error) {
	profiles := make([]string, 0, len(metadata.BuildProfiles))
	for profile := range metadata.BuildProfiles {
		profiles = append(profiles, profile)
	}
	sort.Strings(profiles)
	environmentSet := map[string]struct{}{}
	for _, environment := range metadata.Environments {
		environmentSet[environment] = struct{}{}
	}
	environmentProfiles := map[string]string{}
	for _, profile := range profiles {
		declaration := metadata.BuildProfiles[profile]
		if len(declaration.Environments) == 0 || strings.TrimSpace(declaration.LaunchPolicy) == "" {
			return nil, nil, fmt.Errorf("build_profiles.%s must declare environments and launch_policy", profile)
		}
		for _, environment := range declaration.Environments {
			if _, ok := environmentSet[environment]; !ok {
				return nil, nil, fmt.Errorf("build_profiles.%s references unknown environment %s", profile, environment)
			}
			if previous, exists := environmentProfiles[environment]; exists {
				return nil, nil, fmt.Errorf("environment %s belongs to both %s and %s", environment, previous, profile)
			}
			environmentProfiles[environment] = profile
		}
	}
	return profiles, environmentProfiles, nil
}

func generatedIdentities(metadata appArtifactIdentityMetadata) (map[string]map[string]generatedAppIdentity, []string, error) {
	contract := metadata.ApplicationIdentity
	profiles, _, err := resolveBuildProfiles(metadata)
	if err != nil {
		return nil, nil, err
	}
	identities := map[string]map[string]generatedAppIdentity{}
	targets := []string{}
	for _, profile := range profiles {
		targets = append(targets, profile+"/release")
	}
	for _, environment := range metadata.BuildProfiles["nonprod"].Environments {
		for _, mode := range []string{"debug", "profile"} {
			targets = append(targets, environment+"/"+mode)
		}
	}
	for _, platform := range []string{"android", "ios"} {
		identities[platform] = map[string]generatedAppIdentity{}
		base := contract.BaseApplicationIDs[platform]
		for _, profile := range profiles {
			key := profile + "/release"
			identities[platform][key] = generatedAppIdentity{
				ApplicationID: base.Value + contract.BuildProfileSuffixes[profile],
				DisplayName:   contract.DisplayNameBase + contract.BuildProfileMarks[profile],
				Registered:    base.Registered, BuildProfile: profile, BuildMode: "release", Promotable: profile == "prod",
			}
		}
		for _, environment := range metadata.BuildProfiles["nonprod"].Environments {
			for _, mode := range []string{"debug", "profile"} {
				key := environment + "/" + mode
				identities[platform][key] = generatedAppIdentity{
					ApplicationID: base.Value + "." + environment + contract.BuildModeSuffixes[mode],
					DisplayName:   contract.DisplayNameBase + "·" + strings.ToUpper(environment[:1]) + environment[1:] + contract.BuildModeDisplayMarks[mode],
					Registered:    base.Registered, BuildProfile: "nonprod", BuildMode: mode, Environment: environment, Promotable: false,
				}
			}
		}
	}
	return identities, targets, nil
}

func renderAppIdentityArtifacts(metadata appArtifactIdentityMetadata, sourceSHA string) ([]appIdentityArtifact, error) {
	identities, targets, err := generatedIdentities(metadata)
	if err != nil {
		return nil, err
	}
	buildProfiles, environmentProfiles, err := resolveBuildProfiles(metadata)
	if err != nil {
		return nil, err
	}
	document := generatedAppIdentityDocument{
		Schema: "qwq.app-identity-generated", Source: appIdentityMetadataRelativePath,
		SourceSHA256: "sha256:" + sourceSHA, Environments: append([]string(nil), metadata.Environments...),
		BuildProfiles: buildProfiles, EnvironmentProfiles: environmentProfiles,
		BuildModes: append([]string(nil), metadata.BuildModes...), IdentityTargets: targets, Identities: identities,
	}
	jsonBytes, err := json.MarshalIndent(document, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("encode generated App identity JSON: %w", err)
	}
	artifacts := []appIdentityArtifact{{RelativePath: "android/app/app_identity.generated.json", Content: append(jsonBytes, '\n')}}
	for _, target := range targets {
		identity := identities["ios"][target]
		parts := strings.Split(target, "/")
		configurationTarget := parts[0]
		if identity.BuildMode == "release" {
			configurationTarget = identity.BuildProfile
		}
		configurationName := strings.ToUpper(identity.BuildMode[:1]) + identity.BuildMode[1:] + "-" + configurationTarget
		identityName := configurationTarget + "-" + identity.BuildMode
		identityLines := []string{
			"// Generated from " + appIdentityMetadataRelativePath + "; do not edit.",
			"QWQ_APP_IDENTITY_SOURCE_SHA256 = sha256:" + sourceSHA,
			"QWQ_APP_BUILD_PROFILE = " + identity.BuildProfile,
			strings.TrimRight("QWQ_APP_RUNTIME_ENV = "+identity.Environment, " "),
			"QWQ_IOS_APPLICATION_ID = " + identity.ApplicationID,
			"QWQ_APP_DISPLAY_NAME = " + identity.DisplayName,
			"QWQ_APP_PROMOTABLE = " + fmt.Sprintf("%t", identity.Promotable),
			"",
		}
		artifacts = append(artifacts, appIdentityArtifact{
			RelativePath: filepath.ToSlash(filepath.Join("ios", "Flutter", "Identity", identityName+".xcconfig")),
			Content:      []byte(strings.Join(identityLines, "\n")),
		})
		baseConfigName := "Base/" + strings.ToUpper(identity.BuildMode[:1]) + identity.BuildMode[1:] + ".xcconfig"
		wrapper := strings.Join([]string{
			"// Generated from " + appIdentityMetadataRelativePath + "; do not edit.",
			"#include \"" + baseConfigName + "\"",
			"#include? \"Pods/Target Support Files/Pods-Runner/Pods-Runner." + strings.ToLower(configurationName) + ".xcconfig\"",
			"#include \"Identity/" + identityName + ".xcconfig\"",
			"QWQ_EXPECTED_BUILD_MODE = " + identity.BuildMode,
			"QWQ_EXPECTED_CONFIGURATION = " + configurationName,
			"// FLUTTER_TARGET is owned by Flutter invocation and validated against launch metadata.",
			"",
		}, "\n")
		artifacts = append(artifacts, appIdentityArtifact{
			RelativePath: filepath.ToSlash(filepath.Join("ios", "Flutter", configurationName+".xcconfig")), Content: []byte(wrapper),
		})
	}
	return artifacts, nil
}

func buildAppIdentityGeneratedManifest(artifacts []appIdentityArtifact, sourceSHA string) appIdentityGeneratedManifest {
	outputs := make([]appIdentityManifestOutput, 0, len(artifacts))
	for _, artifact := range artifacts {
		sum := sha256.Sum256(artifact.Content)
		outputs = append(outputs, appIdentityManifestOutput{Path: artifact.RelativePath, SHA256: "sha256:" + hex.EncodeToString(sum[:]), Bytes: len(artifact.Content)})
	}
	sort.Slice(outputs, func(i, j int) bool { return outputs[i].Path < outputs[j].Path })
	return appIdentityGeneratedManifest{Schema: "qwq.app-identity-codegen-manifest", Generator: "tools/codegen_app_metadata --app-identity-only", Source: appIdentityMetadataRelativePath, SourceSHA256: "sha256:" + sourceSHA, Outputs: outputs}
}

func writeAppIdentityArtifacts(appDir, manifestPath string, artifacts []appIdentityArtifact, manifest appIdentityGeneratedManifest) error {
	if previousBytes, err := os.ReadFile(manifestPath); err == nil {
		var previous appIdentityGeneratedManifest
		if json.Unmarshal(previousBytes, &previous) == nil && previous.Schema == "qwq.app-identity-codegen-manifest" {
			current := map[string]struct{}{}
			for _, artifact := range artifacts {
				current[artifact.RelativePath] = struct{}{}
			}
			for _, output := range previous.Outputs {
				if _, retained := current[output.Path]; retained {
					continue
				}
				stalePath := filepath.Clean(filepath.Join(appDir, filepath.FromSlash(output.Path)))
				appRoot := filepath.Clean(appDir) + string(os.PathSeparator)
				if !strings.HasPrefix(stalePath, appRoot) {
					return fmt.Errorf("refuse to remove App identity output outside app root: %s", output.Path)
				}
				if err := os.Remove(stalePath); err != nil && !os.IsNotExist(err) {
					return fmt.Errorf("remove retired App identity artifact %s: %w", stalePath, err)
				}
				fmt.Printf("removed retired generated artifact: %s\n", stalePath)
			}
		}
	}
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
