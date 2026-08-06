// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-004
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestExternalInteractionAccountClosureConsumerIsCanonical(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/external_integration/external_interaction/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents []string `yaml:"source_events"`
			Consumers    []struct {
				Name        string `yaml:"name"`
				Kind        string `yaml:"kind"`
				Facet       string `yaml:"facet"`
				Method      string `yaml:"method"`
				Idempotency string `yaml:"idempotency"`
			} `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.Lifecycle.SourceEvents) != 1 || document.Lifecycle.SourceEvents[0] != "user.user_account.UserAccountClosed" {
		t.Fatalf("external interaction lifecycle sources drifted: %+v", document.Lifecycle.SourceEvents)
	}
	if len(document.Lifecycle.Consumers) != 1 {
		t.Fatalf("lifecycle consumers=%d, want 1", len(document.Lifecycle.Consumers))
	}
	got := document.Lifecycle.Consumers[0]
	if got.Name != "ApplyExternalInteractionAccountClosure" || got.Kind != "event_handler" ||
		got.Facet != "UserAccountClosedProjection" || got.Method != "applyUserAccountClosed" ||
		got.Idempotency != "event_id" {
		t.Fatalf("external interaction event binding drifted: %+v", got)
	}
}
