package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const appLaunchContractTestMetadataDir = "../../contracts/metadata"

// spec_ref: specs/feature-tree/runtime/spec.md#req-001
func TestAppLaunchContractCodegenProjectsCanonicalContractToEveryRuntime(t *testing.T) {
	root := t.TempDir()
	metadataDir := copyAppLaunchContractTestSources(t, root)
	appDir := filepath.Join(root, "quwoquan_app")
	manifestPath := filepath.Join(
		appDir,
		"tool",
		"app_launch_contract_codegen",
		"generated_manifest.json",
	)

	if err := runAppLaunchContractMode(
		metadataDir,
		appDir,
		manifestPath,
		false,
	); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(
		metadataDir,
		appDir,
		manifestPath,
		true,
	); err != nil {
		t.Fatal(err)
	}

	jsonPath := filepath.Join(
		appDir,
		"tool",
		"app_launch_contract_codegen",
		"app_launch_contract.generated.json",
	)
	jsonPayload, err := os.ReadFile(jsonPath)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(jsonPayload, &document); err != nil {
		t.Fatalf("decode neutral App launch contract: %v", err)
	}
	digest, _ := document["sourceDigest"].(string)
	if !strings.HasPrefix(digest, "sha256:") || len(digest) != len("sha256:")+64 {
		t.Fatalf("sourceDigest = %q, want sha256 identity", digest)
	}
	launchManifest, ok := document["appLaunchManifest"].(map[string]any)
	if !ok {
		t.Fatalf("neutral projection misses full appLaunchManifest: %#v", document)
	}
	for _, key := range []string{
		"digest_contract",
		"runtime_config_package",
		"runtime_config_trust",
		"runtime_value_keys",
		"schemas",
	} {
		if _, exists := launchManifest[key]; !exists {
			t.Fatalf("normalized appLaunchManifest misses %q", key)
		}
	}
	artifactContract, ok := document["appArtifactContract"].(map[string]any)
	if !ok {
		t.Fatalf("neutral projection misses appArtifactContract: %#v", document)
	}
	for _, key := range []string{
		"launch_provenances",
		"build_profiles",
		"application_identity",
	} {
		if _, exists := artifactContract[key]; !exists {
			t.Fatalf("normalized appArtifactContract misses %q", key)
		}
	}

	contractValues := collectAppLaunchContractProjectionValues(t, document)
	outputPaths := []string{
		filepath.Join(root, "quwoquan_ops", "cli", "lib", "generated", "app_launch_contract.py"),
		jsonPath,
		filepath.Join(appDir, "lib", "runtime", "config", "generated", "app_launch_contract.g.dart"),
		filepath.Join(appDir, "ios", "Runner", "AppLaunchContract.generated.swift"),
		filepath.Join(
			appDir,
			"android",
			"app",
			"src",
			"runtimeConfigShared",
			"java",
			"com",
			"quwoquan",
			"quwoquan_app",
			"AppLaunchContract.java",
		),
	}
	for _, outputPath := range outputPaths {
		payload, err := os.ReadFile(outputPath)
		if err != nil {
			t.Fatalf("read generated output %s: %v", outputPath, err)
		}
		text := string(payload)
		if !strings.Contains(text, digest) {
			t.Fatalf("generated output %s misses shared source digest %q", outputPath, digest)
		}
		for _, value := range contractValues {
			if !strings.Contains(text, value) {
				t.Fatalf("generated output %s misses canonical value %q", outputPath, value)
			}
		}
	}

	pythonPayload, err := os.ReadFile(outputPaths[0])
	if err != nil {
		t.Fatal(err)
	}
	for _, constant := range []string{
		"APP_LAUNCH_MANIFEST",
		"APP_ARTIFACT_CONTRACT",
		"APP_LAUNCH_ATTEMPT_TERMINAL_STATES",
		"LOCAL_TRANSPORT_TARGETS",
		"RUNTIME_CONFIG_PACKAGE_RUNTIME_REQUIRED_FIELDS",
		"APP_EFFECTIVE_LAUNCH_MANIFEST_TRANSPORT_REQUIRED_FIELDS",
		"RUNTIME_CONFIG_PACKAGE_MAX_LIFETIME_SECONDS",
		"BUILD_PROFILE_ENVIRONMENTS",
		"BUILD_PROFILE_LAUNCH_POLICIES",
		"APP_EFFECTIVE_LAUNCH_MANIFEST_ENTRYPOINT",
		"RUNTIME_CONFIG_ACTIVATION_RECEIPT_STATUSES",
	} {
		if !strings.Contains(string(pythonPayload), constant) {
			t.Fatalf("Python projection misses %s", constant)
		}
	}
	dartPayload, err := os.ReadFile(outputPaths[2])
	if err != nil {
		t.Fatal(err)
	}
	for _, constant := range []string{
		"appLaunchContractSourceDigest",
		"appLaunchProvenances",
		"runtimeConfigSupplyModes",
		"appLaunchLocalTransportTargets",
		"runtimeConfigTrustEnvelopeRequiredFields",
		"appEffectiveLaunchManifestRequiredFields",
	} {
		if !strings.Contains(string(dartPayload), constant) {
			t.Fatalf("Dart projection misses %s", constant)
		}
	}
	javaPayload, err := os.ReadFile(outputPaths[4])
	if err != nil {
		t.Fatal(err)
	}
	for _, constant := range []string{
		"RUNTIME_VALUE_KEYS",
		"LOCAL_TRANSPORT_TARGETS",
		"SCHEMA_VALUES",
		"RUNTIME_CONFIG_TRUST_ENVELOPE_REQUIRED_FIELDS",
		"RUNTIME_CONFIG_PACKAGE_REQUIRED_FIELDS",
		"RUNTIME_CONFIG_ACTIVATION_REQUEST_REQUIRED_FIELDS",
		"RUNTIME_CONFIG_ACTIVATION_RECEIPT_REQUIRED_FIELDS",
		"APP_EFFECTIVE_LAUNCH_MANIFEST_REQUIRED_FIELDS",
		"APP_LAUNCHER_HANDOFF_REQUIRED_FIELDS",
		"RUNTIME_CONFIG_PACKAGE_SIGNATURE_ALGORITHM",
		"RUNTIME_CONFIG_PACKAGE_MAX_FUTURE_SKEW_SECONDS",
		"BUILD_PROFILE_ENVIRONMENTS",
		"BUILD_PROFILE_LAUNCH_POLICIES",
		"APP_EFFECTIVE_LAUNCH_MANIFEST_ENTRYPOINT",
		"RUNTIME_CONFIG_ACTIVATION_RECEIPT_STATUSES",
	} {
		if !strings.Contains(string(javaPayload), constant) {
			t.Fatalf("Java projection misses %s", constant)
		}
	}

	manifestPayload, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	var generatedManifest struct {
		SourceDigest string `json:"sourceDigest"`
		Inputs       []struct {
			Path   string `json:"path"`
			SHA256 string `json:"sha256"`
		} `json:"inputs"`
		Outputs []struct {
			Path   string `json:"path"`
			SHA256 string `json:"sha256"`
		} `json:"outputs"`
	}
	if err := json.Unmarshal(manifestPayload, &generatedManifest); err != nil {
		t.Fatalf("decode freshness manifest: %v", err)
	}
	if generatedManifest.SourceDigest != digest {
		t.Fatalf(
			"freshness manifest sourceDigest = %q, want %q",
			generatedManifest.SourceDigest,
			digest,
		)
	}
	if len(generatedManifest.Inputs) != 2 || len(generatedManifest.Outputs) != 5 {
		t.Fatalf(
			"freshness inventory inputs=%d outputs=%d, want 2/5",
			len(generatedManifest.Inputs),
			len(generatedManifest.Outputs),
		)
	}
	for _, input := range generatedManifest.Inputs {
		if !strings.HasPrefix(input.Path, "quwoquan_service/contracts/metadata/_shared/") ||
			!strings.HasPrefix(input.SHA256, "sha256:") {
			t.Fatalf("non-canonical freshness input: %#v", input)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/spec.md#req-001
func TestAppLaunchContractCodegenRejectsUnknownDuplicateMissingAndDrift(t *testing.T) {
	tests := []struct {
		name       string
		sourceName string
		mutate     func(string) string
		want       string
	}{
		{
			name:       "unknown top-level field",
			sourceName: "app_launch_manifest.yaml",
			mutate: func(source string) string {
				return source + "unknown_launch_contract_field: true\n"
			},
			want: "field unknown_launch_contract_field not found",
		},
		{
			name:       "duplicate YAML field",
			sourceName: "app_launch_manifest.yaml",
			mutate: func(source string) string {
				return source + "schema_id: app_launch_manifest\n"
			},
			want: "duplicate YAML key",
		},
		{
			name:       "empty artifact provenances",
			sourceName: "app_artifact_manifest.yaml",
			mutate: func(source string) string {
				start := strings.Index(source, "\nlaunch_provenances:\n")
				end := strings.Index(source, "\ndistribution_channels:")
				if start < 0 || end <= start {
					return source
				}
				return source[:start] + "\nlaunch_provenances: []" + source[end:]
			},
			want: "launch_provenances is empty",
		},
		{
			name:       "cross-document provenance ref drift",
			sourceName: "app_launch_manifest.yaml",
			mutate: func(source string) string {
				return strings.Replace(
					source,
					"allowed_values_ref: app_artifact_manifest.launch_provenances",
					"allowed_values_ref: local.launch_provenances",
					1,
				)
			},
			want: "app_artifact_manifest.launch_provenances",
		},
		{
			name:       "missing attempt required field",
			sourceName: "app_launch_manifest.yaml",
			mutate: func(source string) string {
				return strings.Replace(source, "      - nonPromotable\n", "", 1)
			},
			want: "schemas.app_launch_attempt.fields",
		},
		{
			name:       "duplicate attempt status",
			sourceName: "app_launch_manifest.yaml",
			mutate: func(source string) string {
				return strings.Replace(
					source,
					"app_launch_attempt_statuses:\n  - prepared\n",
					"app_launch_attempt_statuses:\n  - prepared\n  - prepared\n",
					1,
				)
			},
			want: "duplicate app_launch_attempt_statuses value",
		},
		{
			name:       "missing terminal attempt state",
			sourceName: "app_launch_manifest.yaml",
			mutate: func(source string) string {
				statusesStart := strings.Index(source, "\napp_launch_attempt_statuses:\n")
				forwardStart := strings.Index(source, "\napp_launch_attempt_forward_states:\n")
				forwardEnd := strings.Index(source, "\nruntime_value_keys:")
				if statusesStart < 0 || forwardStart <= statusesStart || forwardEnd <= forwardStart {
					return source
				}
				forwardBody := strings.TrimPrefix(
					source[forwardStart:forwardEnd],
					"\napp_launch_attempt_forward_states:",
				)
				return source[:statusesStart] +
					"\napp_launch_attempt_statuses:" +
					forwardBody +
					source[forwardStart:]
			},
			want: "at least one terminal state",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			metadataDir := copyAppLaunchContractTestSources(t, root)
			path := filepath.Join(metadataDir, "_shared", test.sourceName)
			payload, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			mutated := test.mutate(string(payload))
			if mutated == string(payload) {
				t.Fatalf("test mutation for %s did not change source", test.name)
			}
			if err := os.WriteFile(path, []byte(mutated), 0o644); err != nil {
				t.Fatal(err)
			}
			err = runAppLaunchContractMode(
				metadataDir,
				filepath.Join(root, "quwoquan_app"),
				"",
				false,
			)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("run error = %v, want substring %q", err, test.want)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/spec.md#req-001
func TestAppLaunchContractCodegenCheckRejectsStaleOutputAndManifest(t *testing.T) {
	root := t.TempDir()
	metadataDir := copyAppLaunchContractTestSources(t, root)
	appDir := filepath.Join(root, "quwoquan_app")
	manifestPath := filepath.Join(appDir, "app_launch_contract_manifest.json")
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, false); err != nil {
		t.Fatal(err)
	}

	swiftPath := filepath.Join(appDir, "ios", "Runner", "AppLaunchContract.generated.swift")
	originalSwift, err := os.ReadFile(swiftPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(swiftPath, []byte("// stale\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, true); err == nil ||
		!strings.Contains(err.Error(), "generated App launch contract output is stale") {
		t.Fatalf("stale output check error = %v", err)
	}
	if err := os.WriteFile(swiftPath, originalSwift, 0o644); err != nil {
		t.Fatal(err)
	}

	if err := os.WriteFile(manifestPath, []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, true); err == nil ||
		!strings.Contains(err.Error(), "App launch contract generated manifest is stale") {
		t.Fatalf("stale manifest check error = %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/design.md#failure-semantics
func TestAppLaunchContractCodegenCheckDistinguishesMissingFromUnreadable(t *testing.T) {
	root := t.TempDir()
	metadataDir := copyAppLaunchContractTestSources(t, root)
	appDir := filepath.Join(root, "quwoquan_app")
	manifestPath := filepath.Join(appDir, "app_launch_contract_manifest.json")
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, false); err != nil {
		t.Fatal(err)
	}

	swiftPath := filepath.Join(appDir, "ios", "Runner", "AppLaunchContract.generated.swift")
	if err := os.Remove(swiftPath); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(swiftPath, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, true); err == nil ||
		!strings.Contains(err.Error(), "read generated App launch contract output") ||
		strings.Contains(err.Error(), "is missing") {
		t.Fatalf("unreadable output check error = %v", err)
	}
	if err := os.Remove(swiftPath); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, false); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(manifestPath); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(manifestPath, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(metadataDir, appDir, manifestPath, true); err == nil ||
		!strings.Contains(err.Error(), "read App launch contract generated manifest") ||
		strings.Contains(err.Error(), "is missing") {
		t.Fatalf("unreadable manifest check error = %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/spec.md#req-001
func TestAppLaunchContractSourceDigestBindsCanonicalPathAndRawBytes(t *testing.T) {
	root := t.TempDir()
	metadataDir := copyAppLaunchContractTestSources(t, root)
	appDir := filepath.Join(root, "quwoquan_app")
	if err := runAppLaunchContractMode(metadataDir, appDir, "", false); err != nil {
		t.Fatal(err)
	}
	first := readAppLaunchContractTestDigest(t, appDir)

	launchPath := filepath.Join(metadataDir, "_shared", "app_launch_manifest.yaml")
	payload, err := os.ReadFile(launchPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		launchPath,
		append(payload, []byte("# digest-only raw source change\n")...),
		0o644,
	); err != nil {
		t.Fatal(err)
	}
	if err := runAppLaunchContractMode(metadataDir, appDir, "", false); err != nil {
		t.Fatal(err)
	}
	second := readAppLaunchContractTestDigest(t, appDir)
	if first == second {
		t.Fatalf("source digest did not change after raw source bytes changed: %s", first)
	}
}

// spec_ref: specs/feature-tree/runtime/design.md#single-truth-source
func TestAppLaunchContractProjectsCanonicalValueEvolutionWithoutGoMirror(t *testing.T) {
	root := t.TempDir()
	metadataDir := copyAppLaunchContractTestSources(t, root)
	artifactPath := filepath.Join(metadataDir, "_shared", "app_artifact_manifest.yaml")
	payload, err := os.ReadFile(artifactPath)
	if err != nil {
		t.Fatal(err)
	}
	mutated := strings.Replace(string(payload), "icon_cold_launch", "icon_cold_launch_v2", 1)
	if mutated == string(payload) {
		t.Fatal("canonical provenance mutation did not change source")
	}
	if err := os.WriteFile(artifactPath, []byte(mutated), 0o644); err != nil {
		t.Fatal(err)
	}
	appDir := filepath.Join(root, "quwoquan_app")
	if err := runAppLaunchContractMode(metadataDir, appDir, "", false); err != nil {
		t.Fatalf("canonical value evolution was rejected by a Go mirror: %v", err)
	}
	generated, err := os.ReadFile(filepath.Join(
		appDir,
		"tool",
		"app_launch_contract_codegen",
		"app_launch_contract.generated.json",
	))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(generated), "icon_cold_launch_v2") {
		t.Fatal("generated projection did not preserve evolved canonical provenance")
	}
}

// spec_ref: specs/feature-tree/runtime/spec.md#req-001
func TestAppLaunchContractModeFlagsAndMakeTargetsStayIsolated(t *testing.T) {
	mainSource, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	mainText := string(mainSource)
	for _, flagName := range []string{
		"app-launch-contract-only",
		"check-app-launch-contract",
		"app-launch-contract-manifest",
	} {
		if !strings.Contains(mainText, flagName) {
			t.Fatalf("main.go misses --%s", flagName)
		}
	}
	modeIndex := strings.Index(mainText, "if appLaunchContractOnly {")
	handoffIndex := strings.Index(mainText, "initializeContractGraphBundle(")
	if modeIndex < 0 || handoffIndex < 0 || modeIndex >= handoffIndex {
		t.Fatal("App launch contract mode must return before cloud ContractGraph handoff initialization")
	}

	makeSource, err := os.ReadFile("../../Makefile")
	if err != nil {
		t.Fatal(err)
	}
	makeText := string(makeSource)
	for _, target := range []string{
		"codegen-app-launch-contract: service-contract-view",
		"verify-app-launch-contract: service-contract-view",
	} {
		if !strings.Contains(makeText, target) {
			t.Fatalf("quwoquan_service/Makefile misses isolated target %q", target)
		}
	}
	for _, line := range strings.Split(makeText, "\n") {
		if strings.HasPrefix(line, "codegen-app:") &&
			strings.Contains(line, "app-launch-contract") {
			t.Fatalf("global codegen-app unexpectedly depends on App launch contract target: %s", line)
		}
	}
}

func copyAppLaunchContractTestSources(t *testing.T, root string) string {
	t.Helper()
	metadataDir := filepath.Join(root, "metadata")
	sharedDir := filepath.Join(metadataDir, "_shared")
	if err := os.MkdirAll(sharedDir, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{
		"app_artifact_manifest.yaml",
		"app_launch_manifest.yaml",
	} {
		payload, err := os.ReadFile(filepath.Join(appLaunchContractTestMetadataDir, "_shared", name))
		if err != nil {
			t.Fatalf("read canonical %s: %v", name, err)
		}
		if err := os.WriteFile(filepath.Join(sharedDir, name), payload, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return metadataDir
}

func collectAppLaunchContractProjectionValues(t *testing.T, document map[string]any) []string {
	t.Helper()
	values := []string{}
	appendStrings := func(field string) {
		raw, ok := document[field].([]any)
		if !ok {
			t.Fatalf("neutral projection field %s = %#v, want array", field, document[field])
		}
		for _, value := range raw {
			text, ok := value.(string)
			if !ok {
				t.Fatalf("neutral projection field %s contains %#v", field, value)
			}
			values = append(values, text)
		}
	}
	for _, field := range []string{
		"launchProvenances",
		"localTransportTargets",
		"runtimeConfigSupplyModes",
		"runtimeValueKeys",
		"appLaunchAttemptRequiredFields",
		"appLaunchAttemptStatuses",
		"appLaunchAttemptForwardStates",
		"appLaunchAttemptTerminalStates",
		"runtimeConfigPackageRuntimeRequiredFields",
		"appEffectiveLaunchManifestTransportRequiredFields",
		"runtimeConfigActivationReceiptStatuses",
	} {
		appendStrings(field)
	}
	for _, field := range []string{
		"targetEnvironment",
		"launchBlockers",
		"runtimeConfigErrorCodes",
		"schemaValues",
		"buildProfileLaunchPolicies",
	} {
		raw, ok := document[field].(map[string]any)
		if !ok {
			t.Fatalf("neutral projection field %s = %#v, want object", field, document[field])
		}
		for key, value := range raw {
			text, ok := value.(string)
			if !ok {
				t.Fatalf("neutral projection field %s value %#v is not string", field, value)
			}
			values = append(values, key, text)
		}
	}
	buildProfileEnvironments, ok := document["buildProfileEnvironments"].(map[string]any)
	if !ok {
		t.Fatalf("neutral projection buildProfileEnvironments = %#v, want object", document["buildProfileEnvironments"])
	}
	for profile, raw := range buildProfileEnvironments {
		values = append(values, profile)
		environments, ok := raw.([]any)
		if !ok {
			t.Fatalf("buildProfileEnvironments.%s = %#v, want array", profile, raw)
		}
		for _, environment := range environments {
			text, ok := environment.(string)
			if !ok {
				t.Fatalf("buildProfileEnvironments.%s contains %#v", profile, environment)
			}
			values = append(values, text)
		}
	}
	schemaRequired, ok := document["schemaRequiredFields"].(map[string]any)
	if !ok {
		t.Fatalf("neutral projection schemaRequiredFields = %#v, want object", document["schemaRequiredFields"])
	}
	for schemaName, raw := range schemaRequired {
		values = append(values, schemaName)
		fields, ok := raw.([]any)
		if !ok {
			t.Fatalf("schemaRequiredFields.%s = %#v, want array", schemaName, raw)
		}
		for _, field := range fields {
			text, ok := field.(string)
			if !ok {
				t.Fatalf("schemaRequiredFields.%s contains %#v", schemaName, field)
			}
			values = append(values, text)
		}
	}
	for _, field := range []string{
		"runtimeConfigPackageSignatureAlgorithm",
		"appEffectiveLaunchManifestEntrypoint",
	} {
		value, ok := document[field].(string)
		if !ok {
			t.Fatalf("neutral projection field %s = %#v, want string", field, document[field])
		}
		values = append(values, value)
	}
	return values
}

func readAppLaunchContractTestDigest(t *testing.T, appDir string) string {
	t.Helper()
	payload, err := os.ReadFile(filepath.Join(
		appDir,
		"tool",
		"app_launch_contract_codegen",
		"app_launch_contract.generated.json",
	))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		SourceDigest string `json:"sourceDigest"`
	}
	if err := json.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}
	return document.SourceDigest
}
