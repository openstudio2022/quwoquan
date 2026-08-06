// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestAccountEnforcementDecisionUsesTypedHTTPDeliveryNotEventSubscription(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/product_ops/account_enforcement_case/events.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Events []struct {
			Name              string `yaml:"name"`
			DeliverySemantics string `yaml:"delivery_semantics"`
			Reason            string `yaml:"no_consumer_reason"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.Events) != 1 ||
		document.Events[0].Name != "AccountEnforcementDecisionIssued" ||
		document.Events[0].DeliverySemantics != "synchronous_call" ||
		document.Events[0].Reason == "" {
		t.Fatalf("account enforcement delivery contract drifted: %+v", document.Events)
	}
}
