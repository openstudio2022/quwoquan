// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-claim-request-and-review/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestHomepageRuntimeSourcesMatchComposedProjectors(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	assertHomepageLifecycle(t, root, "homepage", homepageLifecycleContract{
		Idempotency: "command_receipt",
		SourceEvents: []string{
			"entity.homepage_claim_request.HomepageClaimRequested",
			"entity.homepage_claim_request.HomepageClaimReviewed",
			"entity.homepage_status_report.HomepageStatusReported",
			"entity.homepage_status_report.HomepageStatusReportReviewed",
			"entity.homepage_review.HomepageReviewPublished",
			"entity.homepage_review.HomepageReviewUpdated",
			"entity.homepage_review.HomepageReviewRemoved",
		},
		EventConsumers: []homepageEventConsumer{
			{Name: "ApplyHomepageClaimRequested", Kind: "event_handler", Facet: "HomepageLifecycleHandler", Method: "applyClaimRequestedProjection", Idempotency: "event_id"},
			{Name: "ApplyHomepageClaimReviewed", Kind: "event_handler", Facet: "HomepageLifecycleHandler", Method: "applyClaimReviewedProjection", Idempotency: "event_id"},
			{Name: "ApplyHomepageStatusLifecycle", Kind: "event_handler", Facet: "StatusHomepageProjector", Method: "runOnce", Idempotency: "event_id"},
			{Name: "ApplyHomepageReviewSummary", Kind: "event_handler", Facet: "HomepageLifecycleHandler", Method: "applyReviewSummary", Idempotency: "event_id"},
		},
	})
	assertHomepageLifecycle(t, root, "homepage_search_item_view", homepageLifecycleContract{
		SourceEvents: []string{
			"entity.homepage.HomepageCandidateIntaken",
			"entity.homepage.HomepagePublished",
		},
		Checkpoint:  "homepage_source_version",
		Rebuild:     "enumerate_current_homepages_through_canonical_projector",
		Tombstone:   "delete_ineligible_homepage_keep_source_version",
		Idempotency: "aggregate_version",
		EventConsumers: []homepageEventConsumer{
			{Name: "ProjectHomepageSearchItem", Kind: "projector", Facet: "HomepageSearchItemViewProjector", Method: "apply", Idempotency: "aggregate_version"},
		},
	})
}

type homepageEventConsumer struct {
	Name        string `yaml:"name"`
	Kind        string `yaml:"kind"`
	Facet       string `yaml:"facet"`
	Method      string `yaml:"method"`
	Idempotency string `yaml:"idempotency"`
}

type homepageLifecycleContract struct {
	SourceEvents   []string                `yaml:"source_events"`
	Checkpoint     string                  `yaml:"checkpoint"`
	Rebuild        string                  `yaml:"rebuild"`
	Tombstone      string                  `yaml:"tombstone"`
	Idempotency    string                  `yaml:"idempotency"`
	EventConsumers []homepageEventConsumer `yaml:"event_consumers"`
}

func assertHomepageLifecycle(t *testing.T, root, object string, want homepageLifecycleContract) {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(root, "contracts", "entity_homepage", object, "object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle homepageLifecycleContract `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(document.Lifecycle, want) {
		t.Fatalf("%s lifecycle = %#v, want %#v", object, document.Lifecycle, want)
	}
}
