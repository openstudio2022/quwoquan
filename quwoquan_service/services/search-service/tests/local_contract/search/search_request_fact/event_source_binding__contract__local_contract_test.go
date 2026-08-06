// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestSearchRequestFactClosureSubscriptionIsCanonical(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/search/search_request_fact/object.yaml"))
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
	if len(document.Lifecycle.EventConsumers) != 1 {
		t.Fatalf("lifecycle consumers=%d, want 1", len(document.Lifecycle.EventConsumers))
	}
	got := document.Lifecycle.EventConsumers[0]
	if got.Name != "ApplySearchRequestAccountClosure" || got.Kind != "subscription" ||
		len(document.Lifecycle.SourceEvents) != 1 || document.Lifecycle.SourceEvents[0] != "user.user_account.UserAccountClosed" ||
		got.Facet != "UserAccountClosedConsumer" || got.Method != "processOnce" ||
		got.Idempotency != "event_id" {
		t.Fatalf("search request closure binding drifted: %+v", got)
	}
}
