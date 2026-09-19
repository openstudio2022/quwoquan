package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAppIdentityCodegenRendersCompletePlatformMatrix(t *testing.T) {
	metadata := appArtifactIdentityMetadata{
		SchemaID:     "app_artifact_manifest",
		Environments: []string{"alpha", "beta", "gamma", "prod"},
		Platforms:    []string{"android", "ios", "web"},
		BuildModes:   []string{"debug", "profile", "release"},
		BuildProfiles: map[string]appBuildProfileContract{
			"nonprod": {
				Environments: []string{"alpha", "beta", "gamma"},
				LaunchPolicy: "test_live",
			},
			"prod": {
				Environments: []string{"prod"},
				LaunchPolicy: "prod_release",
			},
		},
		ApplicationIdentity: appIdentityContract{
			DisplayNameBase: "趣我圈",
			BaseApplicationIDs: map[string]appIdentityBaseID{
				"android": {Value: "com.leadwise.quwoquan", Registered: true},
				"ios":     {Value: "com.leadwise.quwoquan", Registered: false},
			},
			BuildProfileSuffixes: map[string]string{
				"nonprod": ".nonprod", "prod": "",
			},
			BuildProfileMarks: map[string]string{
				"nonprod": "·非生产", "prod": "",
			},
			BuildModeSuffixes: map[string]string{
				"debug": ".debug", "profile": ".profile",
			},
			BuildModeDisplayMarks: map[string]string{
				"debug": "·调试", "profile": "·性能",
			},
		},
	}

	artifacts, err := renderAppIdentityArtifacts(metadata, strings.Repeat("a", 64))
	if err != nil {
		t.Fatal(err)
	}
	if len(artifacts) != 17 {
		t.Fatalf("artifact count = %d, want 17", len(artifacts))
	}

	byPath := map[string]string{}
	for _, artifact := range artifacts {
		byPath[artifact.RelativePath] = string(artifact.Content)
	}
	android := byPath["android/app/app_identity.generated.json"]
	for _, expected := range []string{
		`"nonprod/release"`, `"prod/release"`, `"alpha/debug"`, `"alpha/profile"`,
		`"beta/debug"`, `"gamma/profile"`, `"applicationId": "com.leadwise.quwoquan.alpha.debug"`,
		`"displayName": "趣我圈·Alpha·调试"`, `"promotable": false`, `"registered": false`,
	} {
		if !strings.Contains(android, expected) {
			t.Fatalf("generated Android identity document misses %s", expected)
		}
	}
	debugAlpha := byPath["ios/Flutter/Debug-alpha.xcconfig"]
	for _, expected := range []string{
		`#include "Base/Debug.xcconfig"`,
		`#include "Identity/alpha-debug.xcconfig"`,
		`QWQ_EXPECTED_CONFIGURATION = Debug-alpha`,
		`FLUTTER_TARGET is owned by Flutter invocation and validated against launch metadata.`,
	} {
		if !strings.Contains(debugAlpha, expected) {
			t.Fatalf("Debug-alpha.xcconfig misses %q", expected)
		}
	}
}

func TestAppIdentityCodegenCheckRejectsStaleArtifact(t *testing.T) {
	root := t.TempDir()
	metadataDir := filepath.Join(root, "metadata")
	appDir := filepath.Join(root, "app")
	manifestPath := filepath.Join(appDir, "tool", "app_identity_codegen", "generated_manifest.json")
	if err := os.MkdirAll(filepath.Join(metadataDir, "_shared"), 0755); err != nil {
		t.Fatal(err)
	}
	metadata := `schema_id: app_artifact_manifest
environments: [alpha, beta, gamma, prod]
platforms: [android, ios, web]
build_modes: [debug, profile, release]
build_profiles:
  nonprod:
    environments: [alpha, beta, gamma]
    launch_policy: test_live
  prod:
    environments: [prod]
    launch_policy: prod_release
application_identity:
  display_name_base: 趣我圈
  base_application_ids:
    android: {value: com.leadwise.quwoquan, registered: true}
    ios: {value: com.leadwise.quwoquan, registered: false}
  build_profile_suffixes: {nonprod: .nonprod, prod: ""}
  build_profile_display_marks: {nonprod: ·非生产, prod: ""}
  build_mode_suffixes: {debug: .debug, profile: .profile}
  build_mode_display_marks: {debug: ·调试, profile: ·性能}
`
	if err := os.WriteFile(filepath.Join(metadataDir, "_shared", "app_artifact_manifest.yaml"), []byte(metadata), 0644); err != nil {
		t.Fatal(err)
	}
	if err := runAppIdentityMode(metadataDir, appDir, manifestPath, false); err != nil {
		t.Fatal(err)
	}
	artifactPath := filepath.Join(appDir, "ios", "Flutter", "Debug-alpha.xcconfig")
	if err := os.WriteFile(artifactPath, []byte("stale\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := runAppIdentityMode(metadataDir, appDir, manifestPath, true); err == nil || !strings.Contains(err.Error(), "stale") {
		t.Fatalf("check error = %v, want stale artifact failure", err)
	}
}
