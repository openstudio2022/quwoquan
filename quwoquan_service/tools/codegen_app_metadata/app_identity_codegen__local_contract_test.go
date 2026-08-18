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
		Platforms:    []string{"android", "ios", "web", "macos"},
		BuildModes:   []string{"debug", "profile", "release"},
		ApplicationIdentity: appIdentityContract{
			DisplayNameBase: "趣我圈",
			BaseApplicationIDs: map[string]appIdentityBaseID{
				"android": {Value: "com.quwoquan.quwoquan_app", Registered: true},
				"ios":     {Value: "com.example.quwoquanApp", Registered: false},
			},
			EnvironmentSuffixes: map[string]string{
				"alpha": ".alpha", "beta": ".beta", "gamma": ".gamma", "prod": "",
			},
			EnvironmentMarks: map[string]string{
				"alpha": "α", "beta": "β", "gamma": "γ", "prod": "",
			},
			BuildModeSuffixes: map[string]string{
				"debug": ".debug", "profile": ".profile", "release": "",
			},
			BuildModeDisplayMarks: map[string]string{
				"debug": "·D", "profile": "·P", "release": "",
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
		`"alpha/debug"`, `"beta/profile"`, `"gamma/release"`, `"prod/release"`,
	} {
		if !strings.Contains(android, expected) {
			t.Fatalf("generated Android identity document misses %s", expected)
		}
	}
	debugAlpha := byPath["ios/Flutter/Debug-alpha.xcconfig"]
	for _, expected := range []string{
		`#include "Debug.xcconfig"`,
		`#include "Identity/alpha.xcconfig"`,
		`QWQ_EXPECTED_CONFIGURATION = Debug-alpha`,
		`QWQ_MODE_BUNDLE_ID_SUFFIX = .debug`,
		`FLUTTER_TARGET = lib/main_prod.dart`,
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
platforms: [android, ios, web, macos]
build_modes: [debug, profile, release]
application_identity:
  display_name_base: 趣我圈
  base_application_ids:
    android: {value: com.quwoquan.quwoquan_app, registered: true}
    ios: {value: com.example.quwoquanApp, registered: false}
  environment_suffixes: {alpha: .alpha, beta: .beta, gamma: .gamma, prod: ""}
  environment_display_marks: {alpha: α, beta: β, gamma: γ, prod: ""}
  build_mode_suffixes: {debug: .debug, profile: .profile, release: ""}
  build_mode_display_marks: {debug: ·D, profile: ·P, release: ""}
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
