// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestObjectTagIndexConsumesOnlyDurableProfileTagFacts(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	objectRaw, err := os.ReadFile(filepath.Join(root, "contracts/tag/object_tag_index_view/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var objectDocument struct {
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
	if err := yaml.Unmarshal(objectRaw, &objectDocument); err != nil {
		t.Fatal(err)
	}
	operationsRaw, err := os.ReadFile(filepath.Join(root, "contracts/tag/object_tag_index_view/operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operationsDocument struct {
		RuntimeEntrypoints []struct {
			Name        string `yaml:"name"`
			Kind        string `yaml:"kind"`
			Application struct {
				Facet  string `yaml:"facet"`
				Method string `yaml:"method"`
			} `yaml:"application"`
		} `yaml:"runtime_entrypoints"`
	}
	if err := yaml.Unmarshal(operationsRaw, &operationsDocument); err != nil {
		t.Fatal(err)
	}
	if len(objectDocument.Lifecycle.EventConsumers) != 1 ||
		len(objectDocument.Lifecycle.SourceEvents) != 1 ||
		objectDocument.Lifecycle.SourceEvents[0] != "user.user_account.UserProfileTagsChanged" {
		t.Fatalf("object tag lifecycle=%+v", objectDocument.Lifecycle)
	}
	consumer := objectDocument.Lifecycle.EventConsumers[0]
	if consumer.Name != "ProjectObjectTagIndex" || consumer.Kind != "projector" ||
		consumer.Facet != "UserProfileTagConsumer" ||
		consumer.Method != "processOnce" || consumer.Idempotency != "aggregate_version" {
		t.Fatalf("object tag consumer binding drifted: %+v", consumer)
	}
	if len(operationsDocument.RuntimeEntrypoints) != 1 {
		t.Fatalf("runtime entrypoints=%d, want 1", len(operationsDocument.RuntimeEntrypoints))
	}
	entrypoint := operationsDocument.RuntimeEntrypoints[0]
	if entrypoint.Name != consumer.Name || entrypoint.Kind != consumer.Kind ||
		entrypoint.Application.Facet != consumer.Facet || entrypoint.Application.Method != consumer.Method {
		t.Fatalf("runtime binding=%+v lifecycle consumer=%+v", entrypoint, consumer)
	}
}
