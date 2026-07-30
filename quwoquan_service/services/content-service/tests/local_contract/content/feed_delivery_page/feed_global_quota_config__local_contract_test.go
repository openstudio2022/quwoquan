// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package feed_delivery_page_test

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"

	rtrec "quwoquan_service/runtime/recommendation"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
)

type feedQuotaConfigEntry struct {
	Key       string `yaml:"key"`
	Reload    string `yaml:"reload"`
	Rollout   string `yaml:"rollout"`
	Sensitive bool   `yaml:"sensitive"`
	Default   any    `yaml:"default"`
}

func TestFeedGlobalQuotaConfigMatchesCanonicalRuntimePolicies(t *testing.T) {
	serviceRoot := contentServiceModuleRoot(t)
	raw, err := os.ReadFile(filepath.Join(
		serviceRoot,
		"services/content-service/config/schema.yaml",
	))
	if err != nil {
		t.Fatalf("read content-service config schema: %v", err)
	}
	var schema struct {
		Configs []feedQuotaConfigEntry `yaml:"configs"`
	}
	if err := yaml.Unmarshal(raw, &schema); err != nil {
		t.Fatalf("decode content-service config schema: %v", err)
	}
	entries := make(map[string]feedQuotaConfigEntry, len(schema.Configs))
	for _, entry := range schema.Configs {
		entries[entry.Key] = entry
	}

	ranked := rtrec.DefaultRankedFeedWindowQuotaPolicy()
	delivery := deliveryredis.DefaultQuotaPolicy()
	want := map[string]int64{
		"sys.content-service.feed.ranked_window_quota_shard_count": int64(
			ranked.ShardCount,
		),
		"sys.content-service.feed.ranked_window_maximum_live_records_per_shard": int64(
			ranked.MaximumLiveRecordsPerShard,
		),
		"sys.content-service.feed.ranked_window_maximum_live_bytes_per_shard": ranked.MaximumLiveBytesPerShard,
		"sys.content-service.feed.delivery_page_quota_shard_count": int64(
			delivery.ShardCount,
		),
		"sys.content-service.feed.delivery_page_maximum_live_records_per_shard": int64(
			delivery.MaximumLiveRecordsPerShard,
		),
		"sys.content-service.feed.delivery_page_maximum_live_bytes_per_shard": delivery.MaximumLiveBytesPerShard,
	}
	for key, defaultValue := range want {
		entry, ok := entries[key]
		if !ok {
			t.Fatalf("feed global quota config %q is missing", key)
		}
		gotDefault, numeric := numericConfigDefault(entry.Default)
		if !numeric || gotDefault != defaultValue ||
			entry.Reload != "restart" ||
			entry.Rollout != "progressive" ||
			entry.Sensitive {
			t.Fatalf(
				"feed global quota config %q=%+v, want default=%d restart/progressive/non-sensitive",
				key,
				entry,
				defaultValue,
			)
		}
	}
	if ranked.MaximumLiveRecords() != 32768 ||
		ranked.MaximumLiveBytes() != 32*1024*1024*1024 {
		t.Fatalf("ranked global bound drifted: %+v", ranked)
	}
	if delivery.MaximumLiveRecords() != 131072 ||
		delivery.MaximumLiveBytes() != 8*1024*1024*1024 {
		t.Fatalf("delivery global bound drifted: %+v", delivery)
	}
}

func numericConfigDefault(value any) (int64, bool) {
	switch typed := value.(type) {
	case int:
		return int64(typed), true
	case int64:
		return typed, true
	case uint64:
		if typed <= uint64(^uint64(0)>>1) {
			return int64(typed), true
		}
	}
	return 0, false
}

func contentServiceModuleRoot(t *testing.T) string {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test file")
	}
	current := filepath.Dir(currentFile)
	for {
		if _, err := os.Stat(filepath.Join(current, "go.mod")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatal("quwoquan_service module root not found")
		}
		current = parent
	}
}
