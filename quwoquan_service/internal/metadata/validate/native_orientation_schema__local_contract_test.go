package validate

// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021
import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

func TestNativeOrientationSchema(t *testing.T) {
	_, file, _, _ := runtime.Caller(0)
	root := filepath.Join(filepath.Dir(file), "../../..")
	payload, err := os.ReadFile(filepath.Join(root, "services/content-service/contracts/media/media_asset/native_orientation_contract.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(document)
	if err := json.Unmarshal(encoded, &document); err != nil {
		t.Fatal(err)
	}
	authoring, err := jsonschema.NewCompiler().Compile(filepath.Join(root, "contracts/metadata/_schemas/native_orientation_contract.schema.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := authoring.Validate(document); err != nil {
		t.Fatal(err)
	}
	document["unknown"] = true
	if authoring.Validate(document) == nil {
		t.Fatal("unknown authoring field accepted")
	}
	delete(document, "unknown")
	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource("https://quwoquan.local/orientation", document["response_schema"]); err != nil {
		t.Fatal(err)
	}
	schema, err := compiler.Compile("https://quwoquan.local/orientation")
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name, payload string
		valid         bool
	}{
		{"android", `{"status":"available","platform":"android","binding":"window-1","axis":"portrait","rotation":180}`, true},
		{"ios", `{"status":"available","platform":"ios","binding":"window-1","orientation":"landscapeRight"}`, true},
		{"unavailable", `{"status":"unavailable","platform":"android"}`, true},
		{"unknown", `{"status":"available","platform":"ios","binding":"window-1","orientation":"portraitUp","extra":1}`, false},
		{"enum", `{"status":"available","platform":"ios","binding":"window-1","orientation":"faceUp"}`, false},
		{"platform", `{"status":"available","platform":"ios","binding":"window-1","axis":"portrait","rotation":0}`, false},
		{"empty", `{"status":"available","platform":"android","binding":" ","axis":"portrait","rotation":0}`, false},
		{"rotation", `{"status":"available","platform":"android","binding":"window-1","axis":"portrait","rotation":45}`, false},
		{"stale", `{"status":"unavailable","platform":"ios","binding":"old"}`, false},
	}
	for _, item := range cases {
		t.Run(item.name, func(t *testing.T) {
			var value any
			if err := json.Unmarshal([]byte(item.payload), &value); err != nil {
				t.Fatal(err)
			}
			if valid := schema.Validate(value) == nil; valid != item.valid {
				t.Fatalf("valid=%v wanted=%v", valid, item.valid)
			}
		})
	}
}
