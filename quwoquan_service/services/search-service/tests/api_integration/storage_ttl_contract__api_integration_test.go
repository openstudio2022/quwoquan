package api_integration

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/search-service/internal/infrastructure/feedbackstore"
	"quwoquan_service/services/search-service/internal/infrastructure/queryheatstore"
	"quwoquan_service/services/search-service/internal/infrastructure/searchsignals"
)

// storageMeta mirrors the TTL-bearing shape of storage.yaml so the infra TTL
// constants stay pinned to the single metadata source (R11 auditable TTL).
type storageMeta struct {
	Collections map[string]struct {
		TTL struct {
			Seconds int `yaml:"seconds"`
		} `yaml:"ttl"`
	} `yaml:"collections"`
	DerivedReadModels map[string]struct {
		TTL struct {
			Seconds int `yaml:"seconds"`
		} `yaml:"ttl"`
	} `yaml:"derived_read_models"`
}

type redisKeyspaceMeta struct {
	KeyPatterns []struct {
		Pattern    string `yaml:"pattern"`
		TTLSeconds int    `yaml:"ttl_seconds"`
	} `yaml:"key_patterns"`
}

func loadStorageMeta(t *testing.T) storageMeta {
	t.Helper()
	path := filepath.Join("..", "..", "..", "..", "contracts", "metadata", "search", "query", "storage.yaml")
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

func loadRedisKeyspaceMeta(t *testing.T) redisKeyspaceMeta {
	t.Helper()
	path := filepath.Join("..", "..", "..", "..", "contracts", "metadata", "_shared", "redis_keyspace.yaml")
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

func TestStorageTTLMatchesMetadata(t *testing.T) {
	meta := loadStorageMeta(t)

	if got := meta.Collections["search_queries"].TTL.Seconds; got != feedbackstore.QueriesTTLSeconds {
		t.Fatalf("search_queries TTL drift: metadata=%d infra=%d", got, feedbackstore.QueriesTTLSeconds)
	}
	if got := meta.Collections["search_feedback_events"].TTL.Seconds; got != feedbackstore.FeedbackTTLSeconds {
		t.Fatalf("search_feedback_events TTL drift: metadata=%d infra=%d", got, feedbackstore.FeedbackTTLSeconds)
	}
	if got := meta.DerivedReadModels["rm_search_term_heat"].TTL.Seconds; got != queryheatstore.HeatTTLSeconds {
		t.Fatalf("rm_search_term_heat TTL drift: metadata=%d infra=%d", got, queryheatstore.HeatTTLSeconds)
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
