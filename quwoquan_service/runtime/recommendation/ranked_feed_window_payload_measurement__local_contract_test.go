// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005
package recommendation

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"
)

func TestRankedFeedWindowPayloadBudgetMeasuredProfiles(t *testing.T) {
	for _, profile := range []struct {
		name     string
		tagCount int
		refCount int
		fits     bool
	}{
		{name: "sparse", tagCount: 3, refCount: 2, fits: true},
		{name: "typical", tagCount: 6, refCount: 3, fits: true},
		{name: "dense", tagCount: 15, refCount: 15, fits: false},
	} {
		t.Run(profile.name, func(t *testing.T) {
			window := measurementRankedFeedWindow(t, 300, profile.tagCount, profile.refCount)
			encoded, err := json.Marshal(window)
			if err != nil {
				t.Fatal(err)
			}
			t.Logf("items=%d tags=%d refs=%d bytes=%d max=%d", len(window.Items), profile.tagCount, profile.refCount, len(encoded), RankedFeedWindowMaxPayloadBytes)
			if got := len(encoded) <= RankedFeedWindowMaxPayloadBytes; got != profile.fits {
				t.Fatalf(
					"payload fit=%v, want %v (bytes=%d max=%d)",
					got,
					profile.fits,
					len(encoded),
					RankedFeedWindowMaxPayloadBytes,
				)
			}
		})
	}
}

func TestRankedFeedWindowRejectsOversizedTopLevelStringBeforeJSONChunk(t *testing.T) {
	window := measurementRankedFeedWindow(t, 1, 1, 1)
	window.Binding.ActorID = strings.Repeat("actor", RankedFeedWindowMaxPayloadBytes/5+1)
	encoded, measuredBytes, err := marshalRankedFeedWindowWithinBudget(
		window,
		RankedFeedWindowMaxPayloadBytes,
	)
	if !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) {
		t.Fatalf("oversized binding error=%v, want payload budget", err)
	}
	if encoded != nil || measuredBytes <= RankedFeedWindowMaxPayloadBytes {
		t.Fatalf("oversized binding encoded=%d measured=%d", len(encoded), measuredBytes)
	}
}

func TestRankedFeedWindowCodeConstantsMatchCanonicalRedisKeyspace(t *testing.T) {
	type keyPattern struct {
		Pattern              string `yaml:"pattern"`
		TTLSeconds           int    `yaml:"ttl_seconds"`
		MaxValueBytes        int    `yaml:"max_value_bytes"`
		MaxItems             int    `yaml:"max_items"`
		DefaultPageDepth     int    `yaml:"default_page_depth"`
		MaxActivePerSubject  int    `yaml:"max_active_per_subject"`
		QuotaIndexPattern    string `yaml:"quota_index_pattern"`
		QuotaMetadataPattern string `yaml:"quota_metadata_pattern"`
		QuotaShardCount      int    `yaml:"quota_shard_count"`
		MaxLiveRecords       int    `yaml:"max_live_records_per_quota_shard"`
		MaxLiveBytes         int64  `yaml:"max_live_bytes_per_quota_shard"`
		GlobalMaxRecords     int64  `yaml:"global_max_live_records"`
		GlobalMaxBytes       int64  `yaml:"global_max_live_bytes"`
		MaxMembers           int    `yaml:"max_members"`
		MaxFields            int    `yaml:"max_fields"`
	}
	var metadata struct {
		KeyPatterns []keyPattern `yaml:"key_patterns"`
	}
	metadataPath := filepath.Join(
		"..",
		"..",
		"contracts",
		"metadata",
		"_shared",
		"redis_keyspace.yaml",
	)
	raw, err := os.ReadFile(metadataPath)
	if err != nil {
		t.Fatalf("read canonical Redis keyspace: %v", err)
	}
	if err := yaml.Unmarshal(raw, &metadata); err != nil {
		t.Fatalf("decode canonical Redis keyspace: %v", err)
	}
	patterns := make(map[string]keyPattern, len(metadata.KeyPatterns))
	for _, pattern := range metadata.KeyPatterns {
		patterns[pattern.Pattern] = pattern
	}
	const windowPatternKey = "rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:<windowId>"
	windowPattern, ok := patterns[windowPatternKey]
	if !ok {
		t.Fatal("canonical ranked feed window key pattern missing")
	}
	if windowPattern.TTLSeconds != int(RankedFeedWindowTTL/time.Second) ||
		windowPattern.MaxValueBytes != RankedFeedWindowMaxPayloadBytes ||
		windowPattern.MaxItems != RankedFeedWindowMaxItems ||
		windowPattern.DefaultPageDepth != RankedFeedWindowDefaultPageDepth ||
		windowPattern.MaxActivePerSubject != RankedFeedWindowMaxActivePerSubject ||
		windowPattern.QuotaIndexPattern != "rec:ranked_feed_window_index:{rfw-<quotaShard>}" ||
		windowPattern.QuotaMetadataPattern != "rec:ranked_feed_window_metadata:{rfw-<quotaShard>}" {
		t.Fatalf("canonical window contract drifted: %+v", windowPattern)
	}
	policy := DefaultRankedFeedWindowQuotaPolicy()
	if windowPattern.QuotaShardCount != policy.ShardCount ||
		windowPattern.MaxLiveRecords != policy.MaximumLiveRecordsPerShard ||
		windowPattern.MaxLiveBytes != policy.MaximumLiveBytesPerShard ||
		windowPattern.GlobalMaxRecords != policy.MaximumLiveRecords() ||
		windowPattern.GlobalMaxBytes != policy.MaximumLiveBytes() {
		t.Fatalf(
			"canonical ranked window global quota drifted: metadata=%+v policy=%+v",
			windowPattern,
			policy,
		)
	}
	indexPattern, ok := patterns[windowPattern.QuotaIndexPattern]
	if !ok {
		t.Fatalf("canonical quota index pattern missing: %q", windowPattern.QuotaIndexPattern)
	}
	if indexPattern.TTLSeconds != int(RankedFeedWindowTTL/time.Second) ||
		indexPattern.MaxMembers != policy.MaximumLiveRecordsPerShard {
		t.Fatalf("canonical quota index contract drifted: %+v", indexPattern)
	}
	metadataPattern, ok := patterns[windowPattern.QuotaMetadataPattern]
	if !ok || metadataPattern.TTLSeconds != int(RankedFeedWindowTTL/time.Second) ||
		metadataPattern.MaxFields != policy.MaximumLiveRecordsPerShard {
		t.Fatalf("canonical quota metadata contract drifted: %+v", metadataPattern)
	}

	var slo struct {
		Metrics map[string]string `yaml:"metrics"`
		SLIs    []struct {
			ID                string `yaml:"id"`
			ObjectiveMaxBytes int    `yaml:"objective_max_bytes"`
		} `yaml:"slis"`
	}
	sloPath := filepath.Join(
		"..",
		"..",
		"services",
		"content-service",
		"observability",
		"slo",
		"recommendation_slo.yaml",
	)
	raw, err = os.ReadFile(sloPath)
	if err != nil {
		t.Fatalf("read recommendation SLO: %v", err)
	}
	if err := yaml.Unmarshal(raw, &slo); err != nil {
		t.Fatalf("decode recommendation SLO: %v", err)
	}
	for key, want := range map[string]string{
		"ranked_feed_window_payload_bytes":         "recommendation_ranked_feed_window_payload_bytes",
		"ranked_feed_window_create_total":          "recommendation_ranked_feed_window_create_total",
		"ranked_feed_window_quota_evictions_total": "recommendation_ranked_feed_window_quota_evictions_total",
	} {
		if got := slo.Metrics[key]; got != want {
			t.Fatalf("recommendation SLO metric %s=%q, want %q", key, got, want)
		}
	}
	payloadObjective := 0
	for _, sli := range slo.SLIs {
		if sli.ID == "ranked_feed_window_payload_p99_bytes" {
			payloadObjective = sli.ObjectiveMaxBytes
			break
		}
	}
	if payloadObjective != RankedFeedWindowMaxPayloadBytes {
		t.Fatalf("recommendation SLO payload objective=%d, want %d", payloadObjective, RankedFeedWindowMaxPayloadBytes)
	}
}

func measurementRankedFeedWindow(t *testing.T, itemCount, tagCount, refCount int) rankedFeedWindow {
	t.Helper()
	createdAt := time.Date(2026, 7, 29, 0, 0, 0, 0, time.UTC)
	window := rankedFeedWindow{
		WindowID:  "rfw_measurement",
		CreatedAt: createdAt, ExpiresAt: createdAt.Add(RankedFeedWindowTTL),
		Binding: rankedFeedWindowBinding{
			SubjectHash: rankedFeedWindowSubjectHash("actor\x00actor-measurement"),
			ActorID:     "actor-measurement", PersonaID: "persona-measurement", SessionID: "session-measurement",
			FeedType: FeedDiscovery, Sort: FeedSortRecommend, Surface: "home", ChannelID: "recommend",
			FeedRequestID: "frq_measurement", ReleaseID: "rel_measurement",
			ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		},
		Provenance: rankedFeedWindowProvenance{
			CandidateWatermark: "sha256:" + strings.Repeat("b", 64), PolicyDigest: "sha256:" + strings.Repeat("c", 64),
			ModelReleaseID: "release-measurement", FeatureSnapshotAt: createdAt.Format(time.RFC3339Nano),
			ScorerPath: "model",
		},
		Attribution:     DeliveryAttribution{FeedRequestID: "frq_measurement", PolicyDigest: "sha256:" + strings.Repeat("c", 64)},
		TerminalOutcome: FeedTerminalSuccess, FailureStage: FailureStageNone,
	}
	for itemIndex := 0; itemIndex < itemCount; itemIndex++ {
		tags := make([]string, 0, tagCount)
		refs := make([]string, 0, refCount)
		for index := 0; index < tagCount; index++ {
			tags = append(tags, fmt.Sprintf("Topic/旅行/地域/川西/景区/measurement-%03d-%02d", itemIndex, index))
		}
		for index := 0; index < refCount; index++ {
			refs = append(refs, fmt.Sprintf("entity:homepage:measurement-%03d-%02d", itemIndex, index))
		}
		candidate := CandidateInput{
			ContentID: fmt.Sprintf("post-measurement-%03d", itemIndex), ContentType: "article",
			AuthorID: fmt.Sprintf("author-measurement-%03d", itemIndex), Tags: tags, EntityRefs: refs,
			RecallPath: "mongo_discovery", ContentVertical: "travel_photography", SupplySource: "data_engineering",
		}
		user := &UserFeatureVector{
			TagAffinities: map[string]float64{}, TopicAffinities: map[string]float64{},
			AudienceAffinities: map[string]float64{}, FormatAffinities: map[string]float64{},
			EntityAffinities: map[string]float64{}, CircleTagAffinities: map[string]float64{},
			EntityInstanceAffinities: map[string]float64{}, AuthorAffinities: map[string]float64{candidate.AuthorID: 0.7},
			TypeENER: map[string]float64{candidate.ContentType: 0.5}, DepthDistribution: map[string]int{"L0": 1, "L1": 2, "L2": 3, "L3": 4, "L4": 5},
		}
		for _, tag := range tags {
			user.TagAffinities[tag] = 0.8
			user.TopicAffinities[tag] = 0.8
			user.AudienceAffinities[tag] = 0.8
			user.FormatAffinities[tag] = 0.8
			user.EntityAffinities[tag] = 0.8
			user.CircleTagAffinities[tag] = 0.8
		}
		for _, ref := range refs {
			user.EntityInstanceAffinities[ref] = 0.8
		}
		item := FeedItem{
			ContentID: candidate.ContentID, ContentType: candidate.ContentType, AuthorID: candidate.AuthorID,
			Title: strings.Repeat("题", 80), Tags: tags, RecallPath: candidate.RecallPath,
			ContentVertical: candidate.ContentVertical, SupplySource: candidate.SupplySource,
			SourceOwner: "qwq_data", ReleaseID: "rel_measurement",
			ManifestDigest: "sha256:" + strings.Repeat("a", 64), LifecycleStatus: "active",
			trainingFeatures: newTrainingFeatureSnapshot(user, candidate, createdAt), rank: itemIndex + 1,
		}
		windowItem, err := newRankedFeedWindowItem(item, itemIndex+1)
		if err != nil {
			t.Fatal(err)
		}
		window.Items = append(window.Items, windowItem)
	}
	return window
}
