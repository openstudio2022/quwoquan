// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-004
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestPushDeliveryPortDoesNotDuplicateExternalInteractionEvents(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/external_integration/push_delivery/events.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Events []any `yaml:"events"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.Events) != 0 {
		t.Fatalf("PushDelivery typed port must not duplicate provider ledger events: %+v", document.Events)
	}
}
