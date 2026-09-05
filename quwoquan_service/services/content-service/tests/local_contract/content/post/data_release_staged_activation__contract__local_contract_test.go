// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestDataReleaseStorageDeclaresVerifiedOnlyActivation(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/content/post/storage.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Collections map[string]struct {
			Role        string `yaml:"role"`
			Description string `yaml:"description"`
		} `yaml:"collections"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	state, ok := document.Collections["data_release_state"]
	if !ok || state.Role != "authoritative" {
		t.Fatalf("data_release_state must be authoritative staged state: %+v", state)
	}
	for _, token := range []string{
		"prepared -> imported -> projected -> verified -> active",
		"verified",
		"previous active",
	} {
		if !strings.Contains(state.Description, token) {
			t.Fatalf("data_release_state description missing %q: %q", token, state.Description)
		}
	}
	receipts, ok := document.Collections["data_release_stage_receipts"]
	if !ok || receipts.Role != "append_only" {
		t.Fatalf("data_release_stage_receipts must be append-only: %+v", receipts)
	}
	for _, token := range []string{"duration", "count", "checkpoint", "first typed blocker"} {
		if !strings.Contains(receipts.Description, token) {
			t.Fatalf("stage receipt description missing %q: %q", token, receipts.Description)
		}
	}
}
