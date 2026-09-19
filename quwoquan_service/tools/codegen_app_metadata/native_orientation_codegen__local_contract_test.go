package main

// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021
import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func orientationTestMetadata(t *testing.T) string {
	t.Helper()
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Join(filepath.Dir(source), "../..")
	dir := t.TempDir()
	for _, pair := range [][2]string{
		{"services/content-service/contracts/media/media_asset/native_orientation_contract.yaml", nativeOrientationMetadataPath},
		{"contracts/metadata/_schemas/native_orientation_contract.schema.json", "_schemas/native_orientation_contract.schema.json"},
	} {
		data, err := os.ReadFile(filepath.Join(root, pair[0]))
		if err != nil {
			t.Fatal(err)
		}
		target := filepath.Join(dir, pair[1])
		if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(target, data, 0644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

func TestNativeOrientationGenerator(t *testing.T) {
	metadata := orientationTestMetadata(t)
	app := filepath.Join(t.TempDir(), "quwoquan_app")
	if err := runNativeOrientationMode(metadata, app, false); err != nil {
		t.Fatal(err)
	}
	if err := runNativeOrientationMode(metadata, app, true); err != nil {
		t.Fatal(err)
	}
	dart := filepath.Join(app, nativeOrientationDartOutput)
	source, err := os.ReadFile(dart)
	if err != nil {
		t.Fatal(err)
	}
	for _, token := range []string{"readInterfaceOrientation", "quwoquan/video_editing", "NativeOrientationObservation", "portraitDown", "rotation", "binding"} {
		if !strings.Contains(string(source), token) {
			t.Errorf("missing %s", token)
		}
	}
	if err := os.WriteFile(dart, []byte("drift"), 0644); err != nil {
		t.Fatal(err)
	}
	if runNativeOrientationMode(metadata, app, true) == nil {
		t.Fatal("freshness accepted drift")
	}
}

func TestNativeOrientationCLI(t *testing.T) {
	metadata := orientationTestMetadata(t)
	app := filepath.Join(t.TempDir(), "quwoquan_app")
	binary := filepath.Join(t.TempDir(), "codegen")
	if output, err := exec.Command("go", "build", "-o", binary, ".").CombinedOutput(); err != nil {
		t.Fatalf("build: %s %v", output, err)
	}
	base := []string{"--metadata-dir", metadata, "--app-dir", app}
	for _, extra := range [][]string{{"--native-orientation-only"}, {"--native-orientation-only", "--check-native-orientation"}} {
		args := append(append([]string{}, base...), extra...)
		if output, err := exec.Command(binary, args...).CombinedOutput(); err != nil {
			t.Fatalf("generate/check: %s %v", output, err)
		}
	}
	for _, extra := range [][]string{{"--check-native-orientation"}, {"--native-orientation-only", "--app-launch-contract-only"}, {"--native-orientation-only", "--shell-navigation-metadata-only"}, {"--native-orientation-only", "--intersection-metadata-only"}, {"--native-orientation-only", "--app-identity-only"}, {"--native-orientation-only", "--realtime-contracts-only"}} {
		args := append(append([]string{}, base...), extra...)
		if exec.Command(binary, args...).Run() == nil {
			t.Fatalf("conflicting CLI accepted: %v", extra)
		}
	}
	source, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	normal := strings.Split(string(source), "if err := initializeContractGraphBundle(")
	if len(normal) != 2 || !strings.Contains(normal[1], "runNativeOrientationMode(metadataDir, appDir, false)") {
		t.Fatal("normal App generation must include orientation outputs")
	}
}

func TestNativeOrientationRejectsUnknownAuthoring(t *testing.T) {
	metadata := orientationTestMetadata(t)
	path := filepath.Join(metadata, nativeOrientationMetadataPath)
	data, _ := os.ReadFile(path)
	if err := os.WriteFile(path, append(data, []byte("unknown: true\n")...), 0644); err != nil {
		t.Fatal(err)
	}
	if runNativeOrientationMode(metadata, filepath.Join(t.TempDir(), "quwoquan_app"), false) == nil {
		t.Fatal("unknown authoring accepted")
	}
}
