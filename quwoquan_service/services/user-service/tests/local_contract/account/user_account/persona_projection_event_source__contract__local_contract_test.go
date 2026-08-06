// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestUserAccountProfileProjectionConsumesPersonaLifecycleOnly(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/account/user_account/object.yaml"))
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
		"user.persona.PersonaCreated",
		"user.persona.PersonaUpdated",
		"user.persona.PersonaRetired",
		"user.persona.PersonaActivated",
	}
	if len(document.Lifecycle.EventConsumers) != 1 ||
		document.Lifecycle.EventConsumers[0].Name != "MaterializeActivePersonaProfile" ||
		document.Lifecycle.EventConsumers[0].Kind != "event_handler" ||
		document.Lifecycle.EventConsumers[0].Facet != "PersonaProfileProjector" ||
		document.Lifecycle.EventConsumers[0].Method != "project" ||
		document.Lifecycle.EventConsumers[0].Idempotency != "aggregate_version" ||
		!reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("user account persona lifecycle binding drifted: %+v", document.Lifecycle)
	}
}
