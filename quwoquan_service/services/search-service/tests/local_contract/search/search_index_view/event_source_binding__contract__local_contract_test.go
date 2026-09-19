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
		"content.post.ContentReleaseFenceChanged",
		"content.post.PostPublished",
		"content.post.PostUpdated",
		"content.post.PostSettingsUpdated",
		"content.post.PostModerationRejected",
		"content.post.PostDeleted",
		"content.post.PostPrivacyRedacted",
		"content.post.PostPurged",
		"ops.experiment.ExperimentPolicyActivated",
		"user.user_account.UserProfileSearchProjectionRequested",
		"user.user_account.UserSuspended",
		"user.user_account.UserRestored",
	}
	wantConsumers := []struct {
		Name        string `yaml:"name"`
		Kind        string `yaml:"kind"`
		Facet       string `yaml:"facet"`
		Method      string `yaml:"method"`
		Idempotency string `yaml:"idempotency"`
	}{
		{Name: "ApplyContentPostLifecycle", Kind: "projector", Facet: "ContentPostLifecycleConsumer", Method: "processOnce", Idempotency: "event_id"},
		{Name: "ApplySearchExperimentPolicy", Kind: "projector", Facet: "ExperimentPolicyConsumer", Method: "processOnce", Idempotency: "event_id"},
		{Name: "ApplyAccountRestriction", Kind: "projector", Facet: "UserAccountRestrictionConsumer", Method: "processOnce", Idempotency: "event_id"},
		{Name: "ApplyUserProfileSearchProjection", Kind: "projector", Facet: "UserProfileSearchProjectionConsumer", Method: "processOnce", Idempotency: "event_id"},
	}
	if !reflect.DeepEqual(document.Lifecycle.EventConsumers, wantConsumers) ||
		!reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("search index lifecycle event binding drifted: %+v", document.Lifecycle)
	}
}
