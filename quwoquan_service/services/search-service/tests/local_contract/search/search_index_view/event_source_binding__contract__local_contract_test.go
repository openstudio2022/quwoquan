// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestSearchIndexProjectionDeclaresOnlyAssembledProductionSources(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/search/search_index_view/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string `yaml:"source_events"`
			EventConsumers []struct {
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
	want := []string{
		"ops.experiment.ExperimentPolicyActivated",
		"user.user_account.UserSuspended",
		"user.user_account.UserRestored",
	}
	if len(document.Lifecycle.EventConsumers) != 2 ||
		document.Lifecycle.EventConsumers[0].Name != "ApplySearchExperimentPolicy" ||
		document.Lifecycle.EventConsumers[0].Kind != "projector" ||
		document.Lifecycle.EventConsumers[0].Facet != "ExperimentPolicyConsumer" ||
		document.Lifecycle.EventConsumers[0].Method != "processOnce" ||
		document.Lifecycle.EventConsumers[0].Idempotency != "event_id" ||
		document.Lifecycle.EventConsumers[1].Name != "ApplyAccountRestriction" ||
		document.Lifecycle.EventConsumers[1].Kind != "projector" ||
		document.Lifecycle.EventConsumers[1].Facet != "UserAccountRestrictionConsumer" ||
		document.Lifecycle.EventConsumers[1].Method != "processOnce" ||
		document.Lifecycle.EventConsumers[1].Idempotency != "event_id" ||
		!reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("search index lifecycle event binding drifted: %+v", document.Lifecycle)
	}
}
