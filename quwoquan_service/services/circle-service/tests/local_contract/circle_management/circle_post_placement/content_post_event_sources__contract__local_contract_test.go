// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestCirclePostPlacementDeclaresContentPostLifecycleSource(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	data, err := os.ReadFile(filepath.Join(serviceRoot, "contracts", "circle_management", "circle_post_placement", "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents []string `yaml:"source_events"`
			Consumers    []struct {
				Name   string `yaml:"name"`
				Facet  string `yaml:"facet"`
				Method string `yaml:"method"`
			} `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	want := []string{
		"content.post.PostSubmittedForReview",
		"content.post.PostPublished",
		"content.post.PostModerationRejected",
		"content.post.PostUpdated",
		"content.post.PostSettingsUpdated",
		"content.post.PostPromotedToWork",
		"content.post.PostDeleted",
		"content.post.PostPrivacyRedacted",
		"content.post.PostPurged",
		"content.post.PostImported",
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, want) ||
		len(document.Lifecycle.Consumers) != 1 ||
		document.Lifecycle.Consumers[0].Name != "ProjectContentPostLifecycle" ||
		document.Lifecycle.Consumers[0].Facet != "ContentPostConsumer" ||
		document.Lifecycle.Consumers[0].Method != "processMessage" {
		t.Fatalf("CirclePostPlacement lifecycle = %#v, want sources %#v", document.Lifecycle, want)
	}
}
