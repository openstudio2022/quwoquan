// spec_ref: specs/feature-tree/global-search-experience/canonical-search-contract/spec.md
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestSearchOwnsReplayableUserProfileProjectionIngestion(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/search/search_index_view/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var object struct {
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
	if err := yaml.Unmarshal(raw, &object); err != nil {
		t.Fatal(err)
	}
	if !containsString(object.Lifecycle.SourceEvents, "user.user_account.UserProfileSearchProjectionRequested") {
		t.Fatal("SearchIndexView does not consume the durable UserProfile projection event")
	}
	found := false
	for _, consumer := range object.Lifecycle.EventConsumers {
		if consumer.Name != "ApplyUserProfileSearchProjection" {
			continue
		}
		found = consumer.Kind == "projector" &&
			consumer.Facet == "UserProfileSearchProjectionConsumer" &&
			consumer.Method == "processOnce" &&
			consumer.Idempotency == "event_id"
	}
	if !found {
		t.Fatal("SearchIndexView has no idempotent UserProfile projection consumer")
	}

	storageRaw, err := os.ReadFile(filepath.Join(root, "contracts/search/search_index_view/storage.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var storage struct {
		Collections map[string]struct {
			Role string `yaml:"role"`
		} `yaml:"collections"`
	}
	if err := yaml.Unmarshal(storageRaw, &storage); err != nil {
		t.Fatal(err)
	}
	if storage.Collections["search_user_profile_projection_inbox"].Role != "append_only" {
		t.Fatal("Search UserProfile ingestion lacks an append-only idempotency inbox")
	}
	if storage.Collections["search_user_profile_projection_watermarks"].Role != "projection" {
		t.Fatal("Search UserProfile ingestion lacks a monotonic replay watermark")
	}
}

func TestLocalSearchUserProfileProjectionSharesTheUserDurableStreamDatabase(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		t.Run(environment, func(t *testing.T) {
			raw, err := os.ReadFile(filepath.Join(root, "environments", environment, "config.yaml"))
			if err != nil {
				t.Fatal(err)
			}
			var config struct {
				Overrides map[string]any `yaml:"overrides"`
			}
			if err := yaml.Unmarshal(raw, &config); err != nil {
				t.Fatal(err)
			}
			if got, exists := config.Overrides["sys.search-service.redis.general.db"]; !exists || got != 0 {
				t.Fatalf("Search UserProfile durable stream Redis DB=%v, want explicit 0", got)
			}
		})
	}
}

func containsString(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
