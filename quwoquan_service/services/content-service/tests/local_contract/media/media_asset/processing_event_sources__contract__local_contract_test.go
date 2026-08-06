// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestMediaProcessingWorkerDeclaresEveryHandledOutboxSource(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	data, err := os.ReadFile(filepath.Join(serviceRoot, "contracts", "media", "media_asset", "object.yaml"))
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
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	want := []string{
		"content.media_asset.MediaAssetCreated",
		"content.media_asset.MediaAssetProcessingUpdated",
		"content.media_asset.MediaAssetAccessPolicyUpdated",
		"content.media_asset.MediaAssetDiscarded",
		"content.media_upload_session.MediaUploadInitialized",
		"content.media_upload_session.MediaUploadCompleted",
		"content.media_upload_session.MediaUploadAborted",
	}
	if !reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("media processing lifecycle sources = %#v, want %#v", document.Lifecycle.SourceEvents, want)
	}
	if len(document.Lifecycle.Consumers) != 1 {
		t.Fatalf("media processing lifecycle consumers = %#v, want one", document.Lifecycle.Consumers)
	}
	consumer := document.Lifecycle.Consumers[0]
	if consumer.Name != "ProcessMediaOutbox" || consumer.Kind != "event_handler" ||
		consumer.Facet != "MediaProcessingHandler" || consumer.Method != "process" ||
		consumer.Idempotency != "event_id" {
		t.Fatalf("media processing lifecycle consumer drifted: %#v", consumer)
	}
}
