// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-object-taxonomy-and-provider-registry/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-002
package api_integration

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/infrastructure/searchsignals"
	"quwoquan_service/services/search-service/internal/search/search_feedback_fact/infrastructure/feedbackstore"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/queryheatstore"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/querylogstore"
)

// storageMeta mirrors the canonical TTL-index shape of storage.yaml so the
// infrastructure constants stay pinned to the same expire_after_seconds.
type storageMeta struct {
	Collections map[string]struct {
		Indexes []struct {
			Name               string `yaml:"name"`
			ExpireAfterSeconds *int   `yaml:"expire_after_seconds"`
		} `yaml:"indexes"`
	} `yaml:"collections"`
}

type redisKeyspaceMeta struct {
	KeyPatterns []struct {
		Pattern    string `yaml:"pattern"`
		TTLSeconds int    `yaml:"ttl_seconds"`
	} `yaml:"key_patterns"`
}

func loadStorageMeta(t *testing.T, object string) storageMeta {
	t.Helper()
	path := filepath.Join(searchServiceRoot(t), "contracts", "search", object, "storage.yaml")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read storage.yaml: %v", err)
	}
	var meta storageMeta
	if err := yaml.Unmarshal(data, &meta); err != nil {
		t.Fatalf("unmarshal storage.yaml: %v", err)
	}
	return meta
}

func loadRecentStorageMeta(t *testing.T) storageMeta {
	t.Helper()
	path := filepath.Join(
		searchServiceRoot(t), "contracts", "search", "recent_search_state", "storage.yaml",
	)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read recent-search storage.yaml: %v", err)
	}
	var meta storageMeta
	if err := yaml.Unmarshal(data, &meta); err != nil {
		t.Fatalf("unmarshal recent-search storage.yaml: %v", err)
	}
	return meta
}

func loadRedisKeyspaceMeta(t *testing.T) redisKeyspaceMeta {
	t.Helper()
	path := filepath.Join(
		searchServiceRoot(t), "..", "..", "contracts", "metadata", "_shared", "redis_keyspace.yaml",
	)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read redis_keyspace.yaml: %v", err)
	}
	var meta redisKeyspaceMeta
	if err := yaml.Unmarshal(data, &meta); err != nil {
		t.Fatalf("unmarshal redis_keyspace.yaml: %v", err)
	}
	return meta
}

func expireAfterSeconds(
	t *testing.T,
	meta storageMeta,
	collection string,
	indexName string,
) int {
	t.Helper()
	definition, ok := meta.Collections[collection]
	if !ok {
		t.Fatalf("collection %s missing from storage.yaml", collection)
	}
	for _, index := range definition.Indexes {
		if index.Name != indexName {
			continue
		}
		if index.ExpireAfterSeconds == nil {
			t.Fatalf("TTL index %s.%s has no expire_after_seconds", collection, indexName)
		}
		return *index.ExpireAfterSeconds
	}
	t.Fatalf("TTL index %s.%s missing from storage.yaml", collection, indexName)
	return 0
}

func TestStorageTTLMatchesMetadata(t *testing.T) {
	meta := loadStorageMeta(t, "search_request_fact")

	if got := expireAfterSeconds(t, meta, "search_queries", "idx_search_queries_created"); got != querylogstore.QueriesTTLSeconds {
		t.Fatalf("search_queries TTL drift: metadata=%d infra=%d", got, querylogstore.QueriesTTLSeconds)
	}
	feedbackMeta := loadStorageMeta(t, "search_feedback_fact")
	if got := expireAfterSeconds(t, feedbackMeta, "search_feedback_events", "ttl_search_feedback_events"); got != feedbackstore.FeedbackTTLSeconds {
		t.Fatalf("search_feedback_events TTL drift: metadata=%d infra=%d", got, feedbackstore.FeedbackTTLSeconds)
	}
	if got := expireAfterSeconds(t, meta, "rm_search_term_heat", "idx_search_term_heat_ttl"); got != queryheatstore.HeatTTLSeconds {
		t.Fatalf("rm_search_term_heat TTL drift: metadata=%d infra=%d", got, queryheatstore.HeatTTLSeconds)
	}
	recentMeta := loadRecentStorageMeta(t)
	if got := expireAfterSeconds(t, recentMeta, "recent_search_receipts", "idx_recent_search_receipts_expire"); got != 0 {
		t.Fatalf("recent_search_receipts expiresAt TTL index must use zero delay, got %d", got)
	}
}

func TestSearchRecommendationSignalStreamTTLMatchesMetadata(t *testing.T) {
	meta := loadRedisKeyspaceMeta(t)
	for _, pattern := range meta.KeyPatterns {
		if pattern.Pattern != searchsignals.StreamName {
			continue
		}
		if pattern.TTLSeconds != searchsignals.StreamTTLSeconds {
			t.Fatalf("search signal stream TTL drift: metadata=%d infra=%d", pattern.TTLSeconds, searchsignals.StreamTTLSeconds)
		}
		return
	}
	t.Fatalf("%s missing from redis_keyspace.yaml", searchsignals.StreamName)
}
