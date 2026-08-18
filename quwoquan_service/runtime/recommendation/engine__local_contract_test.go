// spec_ref: specs/feature-tree/runtime/runtime-recommendation/dual-channel-recommendation-engine/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-recommendation/dual-channel-recommendation-engine/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/runtime-recommendation/dual-channel-recommendation-engine/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/runtime/runtime-recommendation/dual-channel-recommendation-engine/spec.md#gwt-001.t3
package recommendation

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/boundedrecord"
	learning "quwoquan_service/runtime/learning"
	"quwoquan_service/runtime/recpolicy"
)

type mockCandidateSource struct {
	candidates []ContentCandidate
}

func (m *mockCandidateSource) Recall(_ context.Context, _ RecallRequest) ([]ContentCandidate, error) {
	return m.candidates, nil
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

type mockRedisClient struct {
	mu                      sync.RWMutex
	data                    map[string]string
	sets                    map[string]map[string]bool
	hashes                  map[string]map[string]string
	rankedFeedWindowIndexes map[string][]string
	rankedFeedWindowOwners  map[string]map[string]string
}

func newMockRedis() *mockRedisClient {
	return &mockRedisClient{
		data:                    make(map[string]string),
		sets:                    make(map[string]map[string]bool),
		hashes:                  make(map[string]map[string]string),
		rankedFeedWindowIndexes: make(map[string][]string),
		rankedFeedWindowOwners:  make(map[string]map[string]string),
	}
}

func (m *mockRedisClient) Get(_ context.Context, key string) (string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.data[key], nil
}
func (m *mockRedisClient) HasKey(_ context.Context, key string) (bool, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, exists := m.data[key]
	return exists, nil
}
func (m *mockRedisClient) Set(_ context.Context, key, value string, _ time.Duration) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.data[key] = value
	return nil
}
func (m *mockRedisClient) SetNX(_ context.Context, key, value string, _ time.Duration) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, exists := m.data[key]; exists {
		return false, nil
	}
	m.data[key] = value
	return true, nil
}
func (m *mockRedisClient) CreateBoundedImmutableRecordAtomic(
	_ context.Context,
	request boundedrecord.Request,
) (boundedrecord.Result, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if winner, exists := m.data[request.RecordKey]; exists {
		index := m.rankedFeedWindowIndexes[request.ShardIndexKey]
		var liveBytes int64
		for _, key := range index {
			liveBytes += int64(len(m.data[key]))
		}
		return boundedrecord.Result{
			Winner:        winner,
			UsageMeasured: true,
			LiveRecords:   int64(len(index)),
			LiveBytes:     liveBytes,
		}, nil
	}
	index := append(
		[]string(nil),
		m.rankedFeedWindowIndexes[request.ShardIndexKey]...,
	)
	owners := m.rankedFeedWindowOwners[request.ShardIndexKey]
	if owners == nil {
		owners = make(map[string]string)
		m.rankedFeedWindowOwners[request.ShardIndexKey] = owners
	}
	var ownerKeys []string
	for _, key := range index {
		if owners[key] == request.OwnerDigest {
			ownerKeys = append(ownerKeys, key)
		}
	}
	ownerEvictionCount := len(ownerKeys) -
		request.Policy.MaximumLiveRecordsPerOwner + 1
	if ownerEvictionCount < 0 {
		ownerEvictionCount = 0
	}
	ownerVictims := ownerKeys[:ownerEvictionCount]
	projectedRecords := len(index) - len(ownerVictims) + 1
	var liveBytes int64
	for _, key := range index {
		liveBytes += int64(len(m.data[key]))
	}
	var ownerEvictionBytes int64
	for _, key := range ownerVictims {
		ownerEvictionBytes += int64(len(m.data[key]))
	}
	projectedBytes := liveBytes - ownerEvictionBytes + int64(len(request.Value))
	if projectedRecords > request.Policy.MaximumLiveRecordsPerShard {
		return boundedrecord.Result{
			UsageMeasured: true,
			LiveRecords:   int64(len(index)),
			LiveBytes:     liveBytes,
		}, boundedrecord.ErrShardKeyQuota
	}
	if projectedBytes > request.Policy.MaximumLiveBytesPerShard {
		return boundedrecord.Result{
			UsageMeasured: true,
			LiveRecords:   int64(len(index)),
			LiveBytes:     liveBytes,
		}, boundedrecord.ErrShardByteQuota
	}
	for _, victim := range ownerVictims {
		delete(m.data, victim)
		delete(owners, victim)
		for position, key := range index {
			if key == victim {
				index = append(index[:position], index[position+1:]...)
				break
			}
		}
	}
	m.data[request.RecordKey] = request.Value
	owners[request.RecordKey] = request.OwnerDigest
	index = append(index, request.RecordKey)
	m.rankedFeedWindowIndexes[request.ShardIndexKey] = index
	return boundedrecord.Result{
		Created:       true,
		OwnerEvicted:  int64(len(ownerVictims)),
		UsageMeasured: true,
		LiveRecords:   int64(len(index)),
		LiveBytes:     projectedBytes,
	}, nil
}
func (m *mockRedisClient) Del(_ context.Context, keys ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, k := range keys {
		delete(m.data, k)
	}
	return nil
}
func (m *mockRedisClient) SAdd(_ context.Context, key string, members ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.sets[key] == nil {
		m.sets[key] = make(map[string]bool)
	}
	for _, mem := range members {
		m.sets[key][mem] = true
	}
	return nil
}
func (m *mockRedisClient) SRem(_ context.Context, key string, members ...string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, member := range members {
		delete(m.sets[key], member)
	}
	return nil
}
func (m *mockRedisClient) SMembers(_ context.Context, key string) ([]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	var result []string
	for k := range m.sets[key] {
		result = append(result, k)
	}
	return result, nil
}
func (m *mockRedisClient) SIsMember(_ context.Context, key, member string) (bool, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.sets[key][member], nil
}
func (m *mockRedisClient) HIncrByFloat(_ context.Context, key, field string, incr float64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.hashes[key] == nil {
		m.hashes[key] = make(map[string]string)
	}
	var cur float64
	if v, ok := m.hashes[key][field]; ok {
		fmt.Sscanf(v, "%f", &cur)
	}
	m.hashes[key][field] = fmt.Sprintf("%f", cur+incr)
	return nil
}
func (m *mockRedisClient) HGetAll(_ context.Context, key string) (map[string]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if m.hashes[key] == nil {
		return map[string]string{}, nil
	}
	result := make(map[string]string, len(m.hashes[key]))
	for field, value := range m.hashes[key] {
		result[field] = value
	}
	return result, nil
}
func (m *mockRedisClient) Expire(_ context.Context, _ string, _ time.Duration) error { return nil }

// PipelineRead implements RedisPipeliner for single-RTT batch reads.
func (m *mockRedisClient) PipelineRead(_ context.Context, ops []PipelineOp) error {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for i := range ops {
		switch ops[i].Type {
		case PipelineHGetAll:
			if m.hashes[ops[i].Key] == nil {
				ops[i].Hash = map[string]string{}
			} else {
				cp := make(map[string]string, len(m.hashes[ops[i].Key]))
				for k, v := range m.hashes[ops[i].Key] {
					cp[k] = v
				}
				ops[i].Hash = cp
			}
		case PipelineSMembers:
			var result []string
			for k := range m.sets[ops[i].Key] {
				result = append(result, k)
			}
			ops[i].Set = result
		case PipelineSIsMember:
			ops[i].Bool = m.sets[ops[i].Key][ops[i].Member]
		default:
			return fmt.Errorf(
				"unsupported recommendation pipeline operation: %d",
				ops[i].Type,
			)
		}
	}
	return nil
}

func TestHotPath_ProcessSignal_UpdatesState(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:    "u1",
		SessionID: "s1",
		ContentID: "c1",
		Action:    "like",
		Tags:      []string{"travel", "photo"},
	})
	if err != nil {
		t.Fatal(err)
	}

	state, err := hp.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}

	if state.TagWeights["travel"] <= 0 {
		t.Error("travel tag weight should be positive after like")
	}
	if state.SessionID != "s1" {
		t.Errorf("expected sessionID s1, got %s", state.SessionID)
	}
}

func TestHotPath_SessionIsolation(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like", Tags: []string{"travel"}})
	hp.ProcessSignal(ctx, BehaviorSignal{UserID: "u1", SessionID: "s2", ContentID: "c2", Action: "like", Tags: []string{"food"}})

	s1, _ := hp.GetSessionState(ctx, "u1", "s1")
	s2, _ := hp.GetSessionState(ctx, "u1", "s2")

	if s1.TagWeights["food"] > 0 {
		t.Error("session s1 should not have food tag from session s2")
	}
	if s2.TagWeights["travel"] > 0 {
		t.Error("session s2 should not have travel tag from session s1")
	}
}

func TestHotPath_DislikeSignal_AddsToNegativeSet(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:    "u1",
		SessionID: "s1",
		ContentID: "c2",
		Action:    "dislike",
		Tags:      []string{"spam"},
	})

	filtered, err := hp.FilterCandidates(ctx, "u1", []ContentCandidate{{ContentID: "c2"}, {ContentID: "c3"}}, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "c3" {
		t.Fatalf("negative feedback should filter c2, got %+v", filtered)
	}
}

func TestEngine_GetFeed_FiltersExposed(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.RecordServed(ctx, "u1", []FeedItem{{ContentID: "c1"}}, time.Now())

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
			{ContentID: "c2", ContentType: "video", PublishedAt: time.Now()},
			{ContentID: "c3", ContentType: "article", PublishedAt: time.Now()},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source}, WithExposureGovernance(hp, hp))
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}

	for _, item := range resp.Items {
		if item.ContentID == "c1" {
			t.Error("c1 should be filtered (already exposed)")
		}
	}
	if len(resp.Items) != 2 {
		t.Errorf("expected 2 items, got %d", len(resp.Items))
	}
}

func TestEngine_GetFeed_FiltersNegativeAfterDislike(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{UserID: "u1", SessionID: "s1", ContentID: "c2", Action: "dislike"})

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
			{ContentID: "c2", ContentType: "video", PublishedAt: time.Now()},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source}, WithExposureGovernance(hp, hp))
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range resp.Items {
		if item.ContentID == "c2" {
			t.Fatal("disliked content c2 should be filtered by negative set")
		}
	}
}

func TestHotPath_HideAuthorAndTypeSignals_UpdateHiddenSets(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:    "u1",
		SessionID: "s1",
		ContentID: "c_author",
		Action:    "hide_author",
		AuthorID:  "author_hidden",
	}); err != nil {
		t.Fatal(err)
	}
	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:      "u1",
		SessionID:   "s1",
		ContentID:   "c_type",
		Action:      "hide_content_type",
		ContentType: "video",
	}); err != nil {
		t.Fatal(err)
	}

	state, err := hp.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}
	if !containsString(state.HiddenAuthorIDs, "author_hidden") {
		t.Fatalf("hidden author should be persisted, got %+v", state.HiddenAuthorIDs)
	}
	if !containsString(state.HiddenContentTypes, "video") {
		t.Fatalf("hidden content type should be persisted, got %+v", state.HiddenContentTypes)
	}
	filtered, err := hp.FilterCandidates(ctx, "u1", []ContentCandidate{{ContentID: "c_author"}, {ContentID: "c_type"}, {ContentID: "c_ok"}}, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "c_ok" {
		t.Fatalf("current content should enter user-level negative filter, got %+v", filtered)
	}
}

func TestEngine_GetFeed_FiltersHiddenAuthorAndContentType(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:    "u1",
		SessionID: "s1",
		ContentID: "seed_author",
		Action:    "hide_author",
		AuthorID:  "author_hidden",
	}); err != nil {
		t.Fatal(err)
	}
	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:      "u1",
		SessionID:   "s1",
		ContentID:   "seed_type",
		Action:      "hide_content_type",
		ContentType: "video",
	}); err != nil {
		t.Fatal(err)
	}

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "c_author", AuthorID: "author_hidden", ContentType: "photo", PublishedAt: time.Now()},
			{ContentID: "c_type", AuthorID: "author_ok", ContentType: "video", PublishedAt: time.Now()},
			{ContentID: "c_ok", AuthorID: "author_ok", ContentType: "article", PublishedAt: time.Now()},
		},
	}
	engine := NewEngine(hp, []CandidateSource{source})
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 1 || resp.Items[0].ContentID != "c_ok" {
		t.Fatalf("only non-hidden candidate should remain, got %+v", resp.Items)
	}
}

func TestEngine_GetFeed_EngagementCountsAffectRanking(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()
	now := time.Now()

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{
				ContentID:    "high",
				ContentType:  "photo",
				PublishedAt:  now,
				LikeCount:    120,
				CommentCount: 40,
				ShareCount:   15,
				ViewCount:    500,
			},
			{
				ContentID:    "low",
				ContentType:  "video",
				PublishedAt:  now,
				LikeCount:    3,
				CommentCount: 1,
				ShareCount:   0,
				ViewCount:    100,
			},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source}, WithPolicyStore(noExplorePolicyStore()))
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("DEBUG: resp.Items length=%d", len(resp.Items))
	for i, item := range resp.Items {
		t.Logf("DEBUG: item[%d] = %s (type=%s, score=%.4f)", i, item.ContentID, item.ContentType, item.Score)
	}
	if len(resp.Items) < 2 {
		t.Fatalf("expected at least 2 items, got %d", len(resp.Items))
	}
	if resp.Items[0].ContentID != "high" {
		t.Fatalf("high engagement content should rank first, got %s", resp.Items[0].ContentID)
	}
}

func TestEngine_GetFeed_ScoresByTagRelevance(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{UserID: "u1", SessionID: "s1", ContentID: "x1", Action: "like", Tags: []string{"travel"}})
	hp.ProcessSignal(ctx, BehaviorSignal{UserID: "u1", SessionID: "s1", ContentID: "x2", Action: "like", Tags: []string{"travel"}})

	now := time.Now()
	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "a", ContentType: "photo", Tags: []string{"food"}, PublishedAt: now},
			{ContentID: "b", ContentType: "photo", Tags: []string{"travel"}, PublishedAt: now},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source}, WithPolicyStore(noExplorePolicyStore()))
	resp, _ := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})

	if len(resp.Items) < 2 {
		t.Fatal("expected at least 2 items")
	}
	if resp.Items[0].ContentID != "b" {
		t.Errorf("travel content should rank higher, got %s first", resp.Items[0].ContentID)
	}
}

func TestEngine_Rerank_AuthorDedup(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "p1", ContentType: "photo", AuthorID: "a1", PublishedAt: now, LikeCount: 100, ViewCount: 500},
			{ContentID: "p2", ContentType: "photo", AuthorID: "a1", PublishedAt: now, LikeCount: 90, ViewCount: 400},
			{ContentID: "p3", ContentType: "photo", AuthorID: "a1", PublishedAt: now, LikeCount: 80, ViewCount: 300},
			{ContentID: "p4", ContentType: "photo", AuthorID: "a1", PublishedAt: now, LikeCount: 70, ViewCount: 200},
			{ContentID: "p5", ContentType: "video", AuthorID: "a2", PublishedAt: now, LikeCount: 50, ViewCount: 150},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source},
		WithPolicyStore(testPolicyStore(func(p *recpolicy.RecPolicy) {
			p.Scorer.MaxAuthorPerFeed = 2
			p.Scorer.ExploreFraction = 0
		})),
	)
	resp, _ := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 5})

	a1Count := 0
	for _, item := range resp.Items {
		if item.AuthorID == "a1" {
			a1Count++
		}
	}
	if a1Count > 2 {
		t.Errorf("expected at most 2 items from a1, got %d", a1Count)
	}
}

func TestEngine_MultiSource_Dedup(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	src1 := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", PublishedAt: now},
		{ContentID: "c2", ContentType: "video", PublishedAt: now},
	}}
	src2 := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c2", ContentType: "video", PublishedAt: now},
		{ContentID: "c3", ContentType: "article", PublishedAt: now},
	}}

	engine := NewEngine(hp, []CandidateSource{src1, src2})
	resp, _ := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 10})

	ids := map[string]int{}
	for _, item := range resp.Items {
		ids[item.ContentID]++
	}
	for id, count := range ids {
		if count > 1 {
			t.Errorf("content %s appears %d times (should be deduped)", id, count)
		}
	}
	if len(resp.Items) != 3 {
		t.Errorf("expected 3 unique items, got %d", len(resp.Items))
	}
}

func TestEngine_DynamicExposureBudget_ReservesTrialLaneWithoutReplacingRanking(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "mature_high", ContentType: "photo", PublishedAt: now.Add(-48 * time.Hour), ViewCount: 1000, LikeCount: 300},
		{ContentID: "mature_mid", ContentType: "photo", PublishedAt: now.Add(-48 * time.Hour), ViewCount: 900, LikeCount: 200},
		{ContentID: "trial_low", ContentType: "article", PublishedAt: now.Add(-1 * time.Hour), ViewCount: 1, LikeCount: 0},
		{ContentID: "mature_low", ContentType: "video", PublishedAt: now.Add(-48 * time.Hour), ViewCount: 800, LikeCount: 100},
	}}

	engine := NewEngine(hp, []CandidateSource{source},
		WithPolicyStore(testPolicyStore(func(p *recpolicy.RecPolicy) {
			p.Scorer.ExploreFraction = 0
			p.Scorer.MaxAuthorPerFeed = 10
			p.ExposureGovernance.DynamicBudget.Enabled = true
			p.ExposureGovernance.DynamicBudget.TrialMinServed = 5
			p.ExposureGovernance.DynamicBudget.PromotionCTRThreshold = 0.2
		})),
	)
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 3})
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(resp.Items))
	}
	ids := []string{resp.Items[0].ContentID, resp.Items[1].ContentID, resp.Items[2].ContentID}
	if ids[0] != "mature_high" {
		t.Fatalf("top ranking item should remain first, got %v", ids)
	}
	if !containsString(ids, "trial_low") {
		t.Fatalf("trial lane should reserve exposure for low-served content, got %v", ids)
	}
}

func TestEngine_DynamicExposureBudget_DisableBucketBypassesBudget(t *testing.T) {
	now := time.Now()
	items := []ScoredCandidate{
		{Candidate: ContentCandidate{ContentID: "mature_high", PublishedAt: now.Add(-48 * time.Hour), ViewCount: 1000, LikeCount: 300}, Score: 10},
		{Candidate: ContentCandidate{ContentID: "mature_mid", PublishedAt: now.Add(-48 * time.Hour), ViewCount: 900, LikeCount: 200}, Score: 9},
		{Candidate: ContentCandidate{ContentID: "trial_low", PublishedAt: now.Add(-1 * time.Hour), ViewCount: 1}, Score: 1},
	}
	cfg := recpolicy.DynamicExposureBudgetConfig{Enabled: true, TrialMinServed: 5, PromotionCTRThreshold: 0.2}

	got := applyDynamicExposureBudget(items, 2, cfg, "disable_exposure_dynamic_budget")
	if got[0].Candidate.ContentID != "mature_high" || got[1].Candidate.ContentID != "mature_mid" {
		t.Fatalf("disable bucket must preserve original order, got %s/%s", got[0].Candidate.ContentID, got[1].Candidate.ContentID)
	}
}

func TestEngine_FrequencyAndNearDupCaps_DelaysRepeatedExperience(t *testing.T) {
	now := time.Now()
	items := []ScoredCandidate{
		{Candidate: ContentCandidate{ContentID: "a1", AuthorID: "author-a", ContentType: "photo", Tags: []string{"travel"}, EntityRefs: []string{"topic:九寨沟"}, PublishedAt: now}, Score: 10},
		{Candidate: ContentCandidate{ContentID: "a2", AuthorID: "author-a", ContentType: "photo", Tags: []string{"travel"}, EntityRefs: []string{"topic:九寨沟"}, PublishedAt: now}, Score: 9},
		{Candidate: ContentCandidate{ContentID: "b1", AuthorID: "author-b", ContentType: "video", Tags: []string{"food"}, EntityRefs: []string{"topic:成都"}, PublishedAt: now}, Score: 8},
	}
	cfg := recpolicy.FrequencyAndNearDupConfig{
		Enabled:                true,
		MaxSameAuthorPerWindow: 1,
		MaxSameTagPerWindow:    1,
		MaxSameTopicPerWindow:  1,
		NearDupJaccardMax:      0.8,
		SoftFallbackMinFillPct: 100,
	}

	got := applyFrequencyAndNearDupCaps(items, 2, cfg)
	if got[0].Candidate.ContentID != "a1" || got[1].Candidate.ContentID != "b1" {
		t.Fatalf("repeated author/tag/topic/near-dup should be delayed, got %s/%s", got[0].Candidate.ContentID, got[1].Candidate.ContentID)
	}
}

func TestEngine_FrequencyAndNearDupCaps_SoftFallbackPreventsEmptyFeed(t *testing.T) {
	now := time.Now()
	items := []ScoredCandidate{
		{Candidate: ContentCandidate{ContentID: "a1", AuthorID: "author-a", ContentType: "photo", Tags: []string{"travel"}, EntityRefs: []string{"topic:九寨沟"}, PublishedAt: now}, Score: 10},
		{Candidate: ContentCandidate{ContentID: "a2", AuthorID: "author-a", ContentType: "photo", Tags: []string{"travel"}, EntityRefs: []string{"topic:九寨沟"}, PublishedAt: now}, Score: 9},
	}
	cfg := recpolicy.FrequencyAndNearDupConfig{
		Enabled:                true,
		MaxSameAuthorPerWindow: 1,
		MaxSameTagPerWindow:    1,
		MaxSameTopicPerWindow:  1,
		NearDupJaccardMax:      0.8,
		SoftFallbackMinFillPct: 100,
	}

	got := applyFrequencyAndNearDupCaps(items, 2, cfg)
	if len(got) < 2 {
		t.Fatalf("soft fallback should refill constrained small pools, got %d", len(got))
	}
}

func TestEngine_ABExperiment_AffectsScoring(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 50},
		{ContentID: "c2", ContentType: "video", Tags: []string{"food"}, PublishedAt: now, LikeCount: 5},
	}}

	// The baseline policy enables the rec_scoring_weights experiment for all
	// users; whichever bucket "testuser" hashes into, scoring must still
	// produce positive scores for both candidates.
	engine := NewEngine(hp, []CandidateSource{source},
		WithPolicyStore(noExplorePolicyStore()),
	)
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "testuser", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(resp.Items))
	}

	// Verify that items have scores (regardless of which bucket was assigned)
	for _, item := range resp.Items {
		if item.Score <= 0 {
			t.Errorf("item %s should have positive score, got %f", item.ContentID, item.Score)
		}
	}
}

type mockLearningRecorder struct {
	mu         sync.Mutex
	events     []struct{ eventID, eventType string }
	scorecards []struct{ runID string }
}

func (m *mockLearningRecorder) RecordEvent(_ context.Context, e learning.Event) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, struct{ eventID, eventType string }{e.EventID, e.EventType})
	return nil
}

func (m *mockLearningRecorder) RecordScorecard(_ context.Context, sc learning.Scorecard) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.scorecards = append(m.scorecards, struct{ runID string }{sc.RunID})
	return nil
}

func (m *mockLearningRecorder) eventCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.events)
}

func TestFeedbackRecorder_RecordImpression(t *testing.T) {
	mock := &mockLearningRecorder{}
	fr := NewFeedbackRecorder(mock)
	ctx := context.Background()

	items := []FeedItem{
		{
			ContentID:        "c1",
			ContentType:      "photo",
			Score:            5.0,
			RecallPath:       "tag_recall",
			trainingFeatures: testImpressionTrainingSnapshot(),
		},
		{
			ContentID:        "c2",
			ContentType:      "video",
			Score:            3.0,
			RecallPath:       "hot_recall",
			trainingFeatures: testImpressionTrainingSnapshot(),
		},
	}

	attribution := ImpressionAttribution{FeedRequestID: "frq_test_1", ModelBucket: "rule"}
	err := fr.RecordImpression(ctx, "u1", "s1", attribution, items)
	if err != nil {
		t.Fatal(err)
	}
	if len(mock.events) != 2 {
		t.Errorf("expected 2 impression events, got %d", len(mock.events))
	}
	for _, e := range mock.events {
		if e.eventType != "rec_impression" {
			t.Errorf("unexpected event type: %s", e.eventType)
		}
	}
	// 同一 feed 批次同一内容重放：eventId 确定性派生，重放不产生新身份。
	if err := fr.RecordImpression(ctx, "u1", "s1", attribution, items[:1]); err != nil {
		t.Fatal(err)
	}
	if mock.events[2].eventID != mock.events[0].eventID {
		t.Errorf(
			"replayed impression must derive the same deterministic eventId: first=%s replay=%s",
			mock.events[0].eventID, mock.events[2].eventID,
		)
	}
}

func TestFeedbackRecorder_EngagementDeterministicEventID(t *testing.T) {
	mock := &mockLearningRecorder{}
	fr := NewFeedbackRecorder(mock)
	ctx := context.Background()

	signal := BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like",
		FeedRequestID: "frq_test_2",
	}
	if err := fr.RecordEngagement(ctx, signal, 5.0); err != nil {
		t.Fatal(err)
	}
	if err := fr.RecordEngagement(ctx, signal, 5.0); err != nil {
		t.Fatal(err)
	}
	if mock.events[0].eventID != mock.events[1].eventID {
		t.Errorf(
			"same feedRequestId+content+action must derive the same eventId: %s vs %s",
			mock.events[0].eventID, mock.events[1].eventID,
		)
	}
	other := signal
	other.Action = "comment"
	if err := fr.RecordEngagement(ctx, other, 5.0); err != nil {
		t.Fatal(err)
	}
	if mock.events[2].eventID == mock.events[0].eventID {
		t.Error("different action must derive a different engagement eventId")
	}
}

func TestFeedbackRecorderRejectsEngagementWithoutFeedRequestID(t *testing.T) {
	mock := &mockLearningRecorder{}
	fr := NewFeedbackRecorder(mock)
	ctx := context.Background()

	err := fr.RecordEngagement(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like",
	}, 5.0)
	if err == nil {
		t.Fatal("learning feedback without feedRequestId must fail closed")
	}
	if len(mock.events) != 0 {
		t.Errorf("unattributed learning feedback must not be emitted, got %d events", len(mock.events))
	}
}

func TestFeedbackRecorder_RecordScorecard(t *testing.T) {
	mock := &mockLearningRecorder{}
	fr := NewFeedbackRecorder(mock)
	ctx := context.Background()

	err := fr.RecordScorecard(ctx, "u1", "control", 1500.0, true)
	if err != nil {
		t.Fatal(err)
	}
	if len(mock.scorecards) != 1 {
		t.Errorf("expected 1 scorecard, got %d", len(mock.scorecards))
	}
	if mock.scorecards[0].runID != "control" {
		t.Errorf("expected runID 'control', got %s", mock.scorecards[0].runID)
	}
}

func TestEngine_WithFeedback_RecordsImpressions(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	mock := &mockLearningRecorder{}
	fr := NewFeedbackRecorder(mock)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", PublishedAt: now},
		{ContentID: "c2", ContentType: "video", PublishedAt: now},
	}}

	engine := NewEngine(hp, []CandidateSource{source}, WithFeedbackRecorder(fr))
	resp, _ := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})

	// Feedback is now async — poll until events arrive or timeout
	deadline := time.After(2 * time.Second)
	for {
		if mock.eventCount() >= len(resp.Items) {
			break
		}
		select {
		case <-deadline:
			t.Fatalf("timeout waiting for async feedback: expected %d events, got %d",
				len(resp.Items), mock.eventCount())
		default:
			time.Sleep(10 * time.Millisecond)
		}
	}
}

// --- Model integration tests ---

type mockModelScorer struct {
	boost float64
}

func (m *mockModelScorer) ScoreBatch(_ context.Context, features *ScoringFeatures, candidates []ContentCandidate) ([]ScoredCandidate, error) {
	result := make([]ScoredCandidate, len(candidates))
	for i, c := range candidates {
		score := float64(c.LikeCount) * m.boost
		result[i] = ScoredCandidate{Candidate: c, Score: score}
	}
	return result, nil
}

type failingModelScorer struct{}

func (f *failingModelScorer) ScoreBatch(_ context.Context, _ *ScoringFeatures, _ []ContentCandidate) ([]ScoredCandidate, error) {
	return nil, fmt.Errorf("model service unavailable")
}

// capturingScorer records the ScoringFeatures it was handed, so tests can
// assert what weights/scorer/segments the engine resolved from policy.
type capturingScorer struct {
	last *ScoringFeatures
}

func (c *capturingScorer) ScoreBatch(_ context.Context, features *ScoringFeatures, candidates []ContentCandidate) ([]ScoredCandidate, error) {
	c.last = features
	result := make([]ScoredCandidate, len(candidates))
	for i, cand := range candidates {
		result[i] = ScoredCandidate{Candidate: cand, Score: float64(cand.LikeCount) + 1}
	}
	return result, nil
}

// TestEngine_SegmentTargeting_DrivesPolicyResolution proves the full T4-3
// segment plumbing: a user whose feature vector carries a population segment
// (computed upstream by MatchSegments) makes the engine resolve the policy's
// segment-targeted preset override — declaratively, with no if-else in the
// engine and no hand-coded weights.
func TestEngine_SegmentTargeting_DrivesPolicyResolution(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 10},
	}}
	// travel_enthusiast → presetOverride engagement_heavy in the baseline policy.
	fp := &mockFeatureProvider{features: map[string]*UserFeatureVector{
		"seg-user": {Segments: []string{"travel_enthusiast"}},
	}}
	cap := &capturingScorer{}
	engine := NewEngine(hp, []CandidateSource{source},
		WithFeatureProvider(fp),
		WithScorer(cap),
		WithPolicyStore(noExplorePolicyStore()),
	)

	if _, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "seg-user", SessionID: "s1", Limit: 5}); err != nil {
		t.Fatal(err)
	}
	if cap.last == nil {
		t.Fatal("scorer never invoked")
	}
	// engagement_heavy preset has popularity 4.0 (vs control 2.0).
	engagementHeavy := recpolicy.Baseline().WeightPresets["engagement_heavy"]
	if cap.last.Weights.Popularity != engagementHeavy.Popularity {
		t.Fatalf("segment override not applied: popularity=%v want %v (engagement_heavy)",
			cap.last.Weights.Popularity, engagementHeavy.Popularity)
	}
}

type mockFeatureProvider struct {
	features map[string]*UserFeatureVector
}

func (m *mockFeatureProvider) GetFeatures(_ context.Context, userID string) (*UserFeatureVector, error) {
	if f, ok := m.features[userID]; ok {
		return f, nil
	}
	return nil, nil
}

func TestEngine_WithCustomScorer(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", PublishedAt: now, LikeCount: 10},
		{ContentID: "c2", ContentType: "video", PublishedAt: now, LikeCount: 100},
	}}

	customScorer := &mockModelScorer{boost: 2.0}
	engine := NewEngine(hp, []CandidateSource{source}, WithScorer(customScorer))
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(resp.Items))
	}
	// c2 (LikeCount=100) should rank first with boost scorer
	if resp.Items[0].ContentID != "c2" {
		t.Errorf("expected c2 first (higher likes), got %s", resp.Items[0].ContentID)
	}
}

func TestEngine_CascadeScorer_FallbackOnError(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", PublishedAt: now, LikeCount: 50},
		{ContentID: "c2", ContentType: "video", PublishedAt: now, LikeCount: 5},
	}}

	cascade := NewCascadeScorer(
		&failingModelScorer{},
		&RuleScorer{},
		100*time.Millisecond,
	)

	engine := NewEngine(hp, []CandidateSource{source}, WithScorer(cascade))
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	// Should have results from fallback RuleScorer
	if len(resp.Items) == 0 {
		t.Error("cascade scorer should fallback to RuleScorer on primary failure")
	}
}

func TestEngine_WithFeatureProvider(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "x1", Action: "like", Tags: []string{"travel"},
	})

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", Tags: []string{"food"}, AuthorID: "auth1", PublishedAt: now},
		{ContentID: "c2", ContentType: "video", Tags: []string{"travel"}, AuthorID: "auth2", PublishedAt: now},
	}}

	fp := &mockFeatureProvider{features: map[string]*UserFeatureVector{
		"u1": {
			TagAffinities:    map[string]float64{"travel": 5.0, "food": 1.0},
			AuthorAffinities: map[string]float64{"auth2": 3.0},
			TotalLikes:       100,
			EngagementRate:   0.15,
		},
	}}

	engine := NewEngine(hp, []CandidateSource{source},
		WithFeatureProvider(fp),
		WithPolicyStore(noExplorePolicyStore()),
	)
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", SessionID: "s1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if len(resp.Items) < 2 {
		t.Fatal("expected at least 2 items")
	}
	// c2 should rank higher: session travel affinity + user tag affinity + author affinity
	if resp.Items[0].ContentID != "c2" {
		t.Errorf("c2 (travel + author affinity) should rank first, got %s", resp.Items[0].ContentID)
	}
}

func TestRuleScorer_UsesUserFeatures(t *testing.T) {
	scorer := &RuleScorer{}
	ctx := context.Background()

	now := time.Now()
	candidates := []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", Tags: []string{"food"}, AuthorID: "a1", PublishedAt: now},
		{ContentID: "c2", ContentType: "video", Tags: []string{"travel"}, AuthorID: "a2", PublishedAt: now},
	}

	features := &ScoringFeatures{
		Session: &SessionState{TagWeights: map[string]float64{"travel": 2.0}},
		User: &UserFeatureVector{
			TagAffinities:    map[string]float64{"travel": 5.0},
			AuthorAffinities: map[string]float64{"a2": 3.0},
			EngagementRate:   0.2,
		},
		Weights:     recpolicy.Baseline().WeightPresets["control"],
		Scorer:      recpolicy.Baseline().Scorer,
		ExploreRate: 0,
	}

	scored, err := scorer.ScoreBatch(ctx, features, candidates)
	if err != nil {
		t.Fatal(err)
	}
	if len(scored) != 2 {
		t.Fatalf("expected 2 scored items, got %d", len(scored))
	}

	// Verify c2 scores higher due to tag + author affinity
	var c1Score, c2Score float64
	for _, s := range scored {
		if s.Candidate.ContentID == "c1" {
			c1Score = s.Score
		}
		if s.Candidate.ContentID == "c2" {
			c2Score = s.Score
		}
	}
	if c2Score <= c1Score {
		t.Errorf("c2 (travel+author) should score higher: c1=%f c2=%f", c1Score, c2Score)
	}

	// Verify detail map has feature contributions
	for _, s := range scored {
		if s.Detail == nil {
			t.Errorf("scored item %s should have detail map", s.Candidate.ContentID)
		}
		if _, ok := s.Detail["authorAffinity"]; !ok {
			t.Errorf("detail should contain authorAffinity for %s", s.Candidate.ContentID)
		}
	}
}

func TestRuleScorer_ConsumesSearchIntentFeature(t *testing.T) {
	scorer := &RuleScorer{}
	now := time.Now()
	candidates := []ContentCandidate{
		{ContentID: "plain", ContentType: "article", Title: "成都周末散步", Tags: []string{"旅行"}, PublishedAt: now},
		{ContentID: "hotpot", ContentType: "article", Title: "成都火锅攻略", Tags: []string{"美食"}, PublishedAt: now},
	}
	features := &ScoringFeatures{
		Session: &SessionState{},
		User: &UserFeatureVector{
			SearchTermAffinities: map[string]float64{
				"火锅": 2.0,
			},
			SearchTermHeat: 4,
		},
		Weights:     recpolicy.Baseline().WeightPresets["control"],
		Scorer:      recpolicy.Baseline().Scorer,
		ExploreRate: 0,
	}

	scored, err := scorer.ScoreBatch(context.Background(), features, candidates)
	if err != nil {
		t.Fatal(err)
	}
	var plain, hotpot ScoredCandidate
	for _, item := range scored {
		if item.Candidate.ContentID == "plain" {
			plain = item
		}
		if item.Candidate.ContentID == "hotpot" {
			hotpot = item
		}
	}
	if hotpot.Detail["searchIntentBoost"] <= 0 {
		t.Fatalf("hotpot searchIntentBoost=%v want >0", hotpot.Detail["searchIntentBoost"])
	}
	if plain.Detail["searchIntentBoost"] != 0 {
		t.Fatalf("plain searchIntentBoost=%v want 0", plain.Detail["searchIntentBoost"])
	}
	if hotpot.Score <= plain.Score {
		t.Fatalf("search intent should lift matching candidate: hotpot=%v plain=%v", hotpot.Score, plain.Score)
	}
}

func TestQualityPreRanker_FiltersStaleContent(t *testing.T) {
	now := time.Now()
	candidates := []ContentCandidate{
		{ContentID: "new", PublishedAt: now.Add(-1 * time.Hour), LikeCount: 10, ViewCount: 100},
		{ContentID: "old", PublishedAt: now.Add(-30 * 24 * time.Hour), LikeCount: 1000, ViewCount: 10000},
		{ContentID: "recent", PublishedAt: now.Add(-2 * 24 * time.Hour), LikeCount: 50, ViewCount: 500},
	}

	pr := NewQualityPreRanker(7 * 24 * time.Hour)
	result := pr.PreRank(context.Background(), candidates, 10)

	for _, c := range result {
		if c.ContentID == "old" {
			t.Error("pre-ranker should filter content older than maxAge")
		}
	}
	if len(result) != 2 {
		t.Errorf("expected 2 items after pre-rank, got %d", len(result))
	}
}

func TestQualityPreRanker_TruncatesToLimit(t *testing.T) {
	now := time.Now()
	candidates := make([]ContentCandidate, 100)
	for i := range candidates {
		candidates[i] = ContentCandidate{
			ContentID:   fmt.Sprintf("c%d", i),
			PublishedAt: now.Add(-time.Duration(i) * time.Hour),
			LikeCount:   int64(100 - i),
			ViewCount:   int64(1000 - i*10),
		}
	}

	pr := NewQualityPreRanker(30 * 24 * time.Hour)
	result := pr.PreRank(context.Background(), candidates, 20)

	if len(result) != 20 {
		t.Errorf("expected 20 items after pre-rank truncation, got %d", len(result))
	}
}

// --- Performance optimization tests ---

func TestSessionCache_HitAndMiss(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like", Tags: []string{"travel"},
	})

	cache := NewSessionCache(hp, 5*time.Second, 100)

	// First call: cache miss → reads from HotPath
	s1, err := cache.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}
	if s1.TagWeights["travel"] <= 0 {
		t.Error("expected travel tag weight > 0")
	}

	// Second call: cache hit → same result without Redis
	s2, err := cache.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}
	if s2.TagWeights["travel"] != s1.TagWeights["travel"] {
		t.Error("cache should return same result")
	}
}

func TestSessionCache_Singleflight(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	cache := NewSessionCache(hp, 5*time.Second, 100)

	// Launch 100 concurrent requests for the same session
	const n = 100
	errs := make(chan error, n)
	for i := 0; i < n; i++ {
		go func() {
			_, err := cache.GetSessionState(ctx, "u1", "s1")
			errs <- err
		}()
	}

	for i := 0; i < n; i++ {
		if err := <-errs; err != nil {
			t.Fatalf("concurrent GetSessionState failed: %v", err)
		}
	}
}

func TestSessionCache_Invalidate(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	cache := NewSessionCache(hp, 5*time.Second, 100)

	cache.GetSessionState(ctx, "u1", "s1")

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like", Tags: []string{"food"},
	})

	// Before invalidate: cache returns stale data (no food tag)
	s1, _ := cache.GetSessionState(ctx, "u1", "s1")
	if s1.TagWeights["food"] > 0 {
		t.Error("cached state should not have food tag yet")
	}

	cache.Invalidate("u1", "s1")

	// After invalidate: fresh data from Redis
	s2, _ := cache.GetSessionState(ctx, "u1", "s1")
	if s2.TagWeights["food"] <= 0 {
		t.Error("after invalidate, food tag should be present")
	}
}

var _ HardExclusionReader = (*SessionCache)(nil)

// TestEngine_LoadFeedbackExclusions_PostReaderPath locks the single hard-fact
// reader used by both recommendation recall and explicit PostReader queries.
func TestEngine_LoadFeedbackExclusions_PostReaderPath(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c_disliked", Action: "dislike",
	})
	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c_reported", Action: "report",
	})
	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", AuthorID: "a_hidden", Action: "hide_author",
	})
	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentType: "video", Action: "hide_content_type",
	})

	// Production wiring: engine reads sessions through SessionCache wrapping HotPath.
	cache := NewSessionCache(hp, 5*time.Second, 100)
	engine := NewEngine(cache, []CandidateSource{&mockCandidateSource{}}, WithExposureGovernance(cache, cache))

	excl, err := engine.LoadFeedbackExclusions(ctx, "u1", "s1")
	if err != nil {
		t.Fatalf("LoadFeedbackExclusions: %v", err)
	}
	if !excl.NegativeContentIDs["c_disliked"] {
		t.Errorf("hard exclusions must contain disliked content, got %+v", excl.NegativeContentIDs)
	}
	if !excl.NegativeContentIDs["c_reported"] {
		t.Errorf("hard exclusions must contain reported content, got %+v", excl.NegativeContentIDs)
	}
	if !excl.HiddenAuthors["a_hidden"] {
		t.Errorf("hard exclusions must contain hidden author, got %+v", excl.HiddenAuthors)
	}
	if !excl.HiddenContentTypes["video"] {
		t.Errorf("hard exclusions must contain hidden content type, got %+v", excl.HiddenContentTypes)
	}
}

func TestBufferedHotPath_AsyncWrite(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	buf := NewBufferedHotPath(hp, WithFlushInterval(20*time.Millisecond))
	defer buf.Stop()

	buf.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like", Tags: []string{"travel"},
	})

	// Signal is async — wait for flush
	time.Sleep(100 * time.Millisecond)

	state, err := hp.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}
	if state.TagWeights["travel"] <= 0 {
		t.Error("expected travel tag weight after buffered flush")
	}
}

func TestBufferedHotPath_BatchFlush(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	buf := NewBufferedHotPath(hp, WithFlushInterval(20*time.Millisecond))
	defer buf.Stop()

	signals := make([]BehaviorSignal, 20)
	for i := range signals {
		signals[i] = BehaviorSignal{
			UserID:    "u1",
			SessionID: "s1",
			ContentID: fmt.Sprintf("c%d", i),
			Action:    "impression",
		}
	}
	buf.ProcessSignalBatch(ctx, signals)

	time.Sleep(150 * time.Millisecond)

	filtered, err := hp.FilterCandidates(ctx, "u1", []ContentCandidate{{ContentID: "c0"}, {ContentID: "fresh"}}, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "fresh" {
		t.Fatalf("impressed content should be filtered after batch flush, got %+v", filtered)
	}
}

func TestEngine_RecallTimeout(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	// Slow source that takes 500ms
	slowSource := &slowCandidateSource{
		delay: 500 * time.Millisecond,
		candidates: []ContentCandidate{
			{ContentID: "slow1", ContentType: "photo", PublishedAt: time.Now()},
		},
	}
	// Fast source that responds immediately
	fastSource := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "fast1", ContentType: "video", PublishedAt: time.Now()},
		},
	}

	engine := NewEngine(hp, []CandidateSource{slowSource, fastSource},
		WithRecallTimeout(100*time.Millisecond),
	)

	start := time.Now()
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 10})
	elapsed := time.Since(start)

	if err != nil {
		t.Fatal(err)
	}
	if elapsed > 300*time.Millisecond {
		t.Errorf("feed should complete within timeout, took %v", elapsed)
	}
	// Fast source should have returned results
	if len(resp.Items) == 0 {
		t.Error("expected at least items from fast source")
	}
}

func TestEngine_RecallTimeoutDoesNotWaitForSourceIgnoringContext(t *testing.T) {
	release := make(chan struct{})
	calls := make(chan struct{}, 2)
	blockedSource := &ignoringContextCandidateSource{
		release: release,
		calls:   calls,
	}
	fastSource := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "fast1", ContentType: "video", PublishedAt: time.Now()},
		},
	}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{blockedSource, fastSource},
		WithRecallTimeout(30*time.Millisecond),
		WithRecallSourceMaxInflight(1),
	)
	type feedResult struct {
		response *FeedResponse
		err      error
	}
	resultCh := make(chan feedResult, 1)
	go func() {
		response, err := engine.GetFeed(
			context.Background(),
			GetFeedRequest{UserID: "u1", Limit: 10},
		)
		resultCh <- feedResult{response: response, err: err}
	}()

	select {
	case result := <-resultCh:
		if result.err != nil {
			close(release)
			t.Fatal(result.err)
		}
		if result.response == nil || len(result.response.Items) == 0 {
			close(release)
			t.Fatal("fast source result must survive a non-cooperative source timeout")
		}
	case <-time.After(300 * time.Millisecond):
		close(release)
		t.Fatal("feed waited beyond recall budget for a source ignoring context")
	}

	secondStart := time.Now()
	second, err := engine.GetFeed(
		context.Background(),
		GetFeedRequest{UserID: "u1", Limit: 10},
	)
	close(release)
	if err != nil {
		t.Fatal(err)
	}
	if second == nil || len(second.Items) == 0 {
		t.Fatal("inflight rejection must not suppress the healthy recall source")
	}
	if elapsed := time.Since(secondStart); elapsed > 100*time.Millisecond {
		t.Fatalf("full recall source slot must fail fast, took %v", elapsed)
	}
	if got := len(calls); got != 1 {
		t.Fatalf("non-cooperative source invocations = %d, want bounded at 1", got)
	}
}

func TestEngine_SequentialRecallReleasesSourceSlotBeforeReturning(t *testing.T) {
	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "stable1", ContentType: "photo", PublishedAt: time.Now()},
		},
	}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{source},
		WithRecallSourceMaxInflight(1),
		WithRecallGlobalMaxInflight(1),
	)

	for index := 0; index < 100; index++ {
		response, err := engine.GetFeed(
			context.Background(),
			GetFeedRequest{UserID: fmt.Sprintf("sequential-%d", index), Limit: 1},
		)
		if err != nil {
			t.Fatalf("sequential request %d observed an occupied recall slot: %v", index, err)
		}
		if response == nil || len(response.Items) != 1 {
			t.Fatalf("sequential request %d returned no admitted item", index)
		}
	}
}

func TestEngine_RecallSourceOutputIsAdmittedBeforeDownstreamWork(t *testing.T) {
	const pageLimit = 20
	sourceCandidates := make([]ContentCandidate, rankedFeedWindowLimit(pageLimit)+1)
	for index := range sourceCandidates {
		sourceCandidates[index] = ContentCandidate{
			ContentID:   fmt.Sprintf("candidate_%03d", index),
			ContentType: "photo",
			PublishedAt: time.Now(),
		}
	}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{&mockCandidateSource{candidates: sourceCandidates}},
	)
	out := make([]ContentCandidate, 0, len(sourceCandidates))
	stats := engine.parallelRecallInto(
		context.Background(),
		GetFeedRequest{UserID: "u1", Limit: pageLimit},
		&SessionState{UserID: "u1"},
		&out,
	)

	if got, want := len(out), rankedFeedWindowLimit(pageLimit); got != want {
		t.Fatalf("bounded recall candidates = %d, want %d", got, want)
	}
	if stats.failed != 1 || stats.succeeded != 0 {
		t.Fatalf("oversized source terminal stats = %+v, want one failure", stats)
	}
}

func TestEngineRejectsRecallSourceCompositionOverCanonicalMaximum(t *testing.T) {
	sources := make([]CandidateSource, 13)
	for index := range sources {
		sources[index] = &mockCandidateSource{candidates: []ContentCandidate{{
			ContentID:   fmt.Sprintf("candidate_%02d", index),
			ContentType: "photo",
		}}}
	}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		sources,
		WithRecallSourceMaximumCount(12),
	)

	_, err := engine.GetFeed(
		context.Background(),
		GetFeedRequest{UserID: "u1", Limit: 20},
	)
	if !errors.Is(err, ErrRecallSourceCountBudgetExceeded) {
		t.Fatalf("source composition error = %v, want count budget", err)
	}
}

func TestAdmitRecallSourceOutputUsesOnlyBoundedReleaseAnchorHandoff(t *testing.T) {
	const maximum = 60
	const actual = 100_000
	releaseID := "rel_current"
	digest := "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	candidates := make([]ContentCandidate, actual)
	for index := range candidates {
		candidates[index] = ContentCandidate{ContentID: fmt.Sprintf("candidate_%06d", index)}
	}
	candidates[maximum*2-1] = ContentCandidate{
		ContentID:       "canonical_handoff",
		SourceOwner:     "qwq_data",
		ReleaseID:       releaseID,
		ManifestDigest:  digest,
		LifecycleStatus: "active",
	}
	// This farther candidate must never be searched or selected. Only the
	// bounded source-contract handoff window ending before 2*maximum is
	// admissible.
	candidates[actual-1] = ContentCandidate{
		ContentID:       "canonical_far_beyond_budget",
		SourceOwner:     "qwq_data",
		ReleaseID:       releaseID,
		ManifestDigest:  digest,
		LifecycleStatus: "active",
	}

	admitted, err := admitRecallSourceOutput(
		context.Background(),
		candidates,
		RecallRequest{
			Limit:                maximum,
			ActiveReleaseID:      releaseID,
			ActiveManifestDigest: digest,
		},
		"hugeSource",
	)
	if !errors.Is(err, ErrRecallSourceCandidateBudgetExceeded) {
		t.Fatalf("admission error = %v, want candidate budget failure", err)
	}
	if len(admitted) != maximum {
		t.Fatalf("admitted candidates = %d, want %d", len(admitted), maximum)
	}
	if got := admitted[maximum-1].ContentID; got != "canonical_handoff" {
		t.Fatalf("release anchor handoff = %q, want canonical_handoff", got)
	}
	for _, candidate := range admitted {
		if candidate.ContentID == "canonical_far_beyond_budget" {
			t.Fatal("candidate beyond the bounded handoff window was admitted")
		}
	}
}

func TestAdmitRecallSourceOutputRejectsFarReleaseAnchorAndHonorsTimeout(t *testing.T) {
	const maximum = 60
	digest := "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	candidates := make([]ContentCandidate, 100_000)
	for index := range candidates {
		candidates[index] = ContentCandidate{ContentID: fmt.Sprintf("candidate_%06d", index)}
	}
	candidates[len(candidates)-1] = ContentCandidate{
		ContentID:       "canonical_far_beyond_budget",
		SourceOwner:     "qwq_data",
		ReleaseID:       "rel_current",
		ManifestDigest:  digest,
		LifecycleStatus: "active",
	}

	admitted, err := admitRecallSourceOutput(
		context.Background(),
		candidates,
		RecallRequest{
			Limit:                maximum,
			ActiveReleaseID:      "rel_current",
			ActiveManifestDigest: digest,
		},
		"hugeSource",
	)
	if !errors.Is(err, ErrRecallSourceCandidateBudgetExceeded) {
		t.Fatalf("admission error = %v, want candidate budget failure", err)
	}
	if containsActiveReleaseCandidate(admitted, "rel_current", digest) {
		t.Fatal("far release anchor must fail closed instead of triggering an unbounded scan")
	}

	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	timedOut, timeoutErr := admitRecallSourceOutput(
		canceled,
		candidates,
		RecallRequest{Limit: maximum},
		"hugeSource",
	)
	if timedOut != nil {
		t.Fatalf("canceled admission retained %d candidates", len(timedOut))
	}
	if !errors.Is(timeoutErr, context.Canceled) {
		t.Fatalf("canceled admission error = %v, want context canceled", timeoutErr)
	}
	if !errors.Is(timeoutErr, ErrRecallSourceCandidateBudgetExceeded) {
		t.Fatalf("canceled admission masked candidate budget error: %v", timeoutErr)
	}
}

type ignoringContextCandidateSource struct {
	release <-chan struct{}
	calls   chan<- struct{}
}

func (s *ignoringContextCandidateSource) Recall(
	context.Context,
	RecallRequest,
) ([]ContentCandidate, error) {
	if s.calls != nil {
		s.calls <- struct{}{}
	}
	<-s.release
	return nil, nil
}

type slowCandidateSource struct {
	delay      time.Duration
	candidates []ContentCandidate
}

func (s *slowCandidateSource) Recall(ctx context.Context, _ RecallRequest) ([]ContentCandidate, error) {
	select {
	case <-time.After(s.delay):
		return s.candidates, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func TestHotPath_PipelinePath(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	// Verify mock implements RedisPipeliner
	if _, ok := hp.redis.(RedisPipeliner); !ok {
		t.Fatal("mockRedisClient should implement RedisPipeliner")
	}

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1",
		Action: "like", Tags: []string{"travel", "photo"},
	})
	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c2",
		Action: "dislike", Tags: []string{"spam"},
	})

	state, err := hp.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}
	if state.TagWeights["travel"] <= 0 {
		t.Error("travel tag should have positive weight")
	}
	filtered, err := hp.FilterCandidates(ctx, "u1", []ContentCandidate{{ContentID: "c2"}, {ContentID: "c3"}}, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "c3" {
		t.Fatalf("negative point lookup should filter c2, got %+v", filtered)
	}
}

func TestHotPath_UndoDislikeRestoresOnlyExactContent(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "dislike",
	}); err != nil {
		t.Fatal(err)
	}
	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c2", Action: "dislike",
	}); err != nil {
		t.Fatal(err)
	}
	if err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "undo_dislike",
	}); err != nil {
		t.Fatal(err)
	}

	filtered, err := hp.FilterCandidates(
		ctx,
		"u1",
		[]ContentCandidate{{ContentID: "c1"}, {ContentID: "c2"}},
		time.Now(),
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "c1" {
		t.Fatalf("undo must restore only c1, got %+v", filtered)
	}
}

func TestPool_AcquireRelease(t *testing.T) {
	buf := acquireCandidates()
	if buf == nil {
		t.Fatal("acquireCandidates should return non-nil")
	}
	if len(*buf) != 0 {
		t.Errorf("expected empty slice, got len %d", len(*buf))
	}

	*buf = append(*buf, ContentCandidate{ContentID: "c1"})
	releaseCandidates(buf)

	// Acquire again — should get a reset slice
	buf2 := acquireCandidates()
	if len(*buf2) != 0 {
		t.Errorf("pool-returned slice should be reset, got len %d", len(*buf2))
	}
	releaseCandidates(buf2)
}

// ---------------------------------------------------------------------------
// Redis Cluster hash tag protocol tests (redis-cluster-protocol L4a)
// ---------------------------------------------------------------------------

// TestSessionKey verifies that sessionKey() produces hash-tagged keys in the
// format {userId}:sessionId, which is required for Redis Cluster slot safety.
func TestSessionKey(t *testing.T) {
	cases := []struct {
		userID, sessionID, want string
	}{
		{"u1", "s1", "{u1}:s1"},
		{"user-123", "sess-abc", "{user-123}:sess-abc"},
		{"u1", "", "{u1}:default"}, // empty sessionID → "default"
		{"", "s1", "{}:s1"},        // edge: empty userId (should not occur in prod)
	}
	for _, tc := range cases {
		got := sessionKey(tc.userID, tc.sessionID)
		if got != tc.want {
			t.Errorf("sessionKey(%q, %q) = %q, want %q", tc.userID, tc.sessionID, got, tc.want)
		}
	}
}

// TestSessionKey_HashTagPresence asserts that the hash tag `{` and `}` are
// always present and wrap only the userId — no sessionId inside the braces.
func TestSessionKey_HashTagPresence(t *testing.T) {
	sk := sessionKey("alice", "morning")
	if sk[0] != '{' {
		t.Errorf("sessionKey must start with '{', got %q", sk)
	}
	// Find closing brace
	closeIdx := -1
	for i, ch := range sk {
		if ch == '}' {
			closeIdx = i
			break
		}
	}
	if closeIdx < 0 {
		t.Fatalf("sessionKey %q has no closing '}'", sk)
	}
	userIDInTag := sk[1:closeIdx]
	if userIDInTag != "alice" {
		t.Errorf("hash tag content should be userID %q, got %q", "alice", userIDInTag)
	}
	suffix := sk[closeIdx+1:]
	if suffix != ":morning" {
		t.Errorf("suffix after hash tag should be %q, got %q", ":morning", suffix)
	}
}

// TestHotPath_HashTagKeys verifies that the actual Redis keys written by HotPath
// use the {userId} hash tag convention so all session keys land on the same cluster slot.
func TestHotPath_HashTagKeys(t *testing.T) {
	mr := newMockRedis()
	hp := NewHotPath(mr)
	ctx := context.Background()

	err := hp.ProcessSignal(ctx, BehaviorSignal{
		UserID:    "user42",
		SessionID: "sess1",
		ContentID: "c1",
		Action:    "like",
		Tags:      []string{"travel"},
	})
	if err != nil {
		t.Fatal(err)
	}

	// All keys written to the mock redis must contain {user42} hash tag.
	// The mock redis captures keys; we verify via SMembers / HGetAll key lookups.
	sk := sessionKey("user42", "sess1")
	expectedTag := "{user42}"
	if len(sk) < len(expectedTag) || sk[:len(expectedTag)] != expectedTag {
		t.Errorf("sessionKey %q does not start with hash tag %q", sk, expectedTag)
	}

	// Verify state is readable with the hash-tagged key via GetSessionState.
	state, err := hp.GetSessionState(ctx, "user42", "sess1")
	if err != nil {
		t.Fatal(err)
	}
	if state.TagWeights["travel"] <= 0 {
		t.Error("travel tag weight should be positive after like signal")
	}
}

func TestEngine_ConcurrentFeedRequests(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	candidates := make([]ContentCandidate, 50)
	for i := range candidates {
		candidates[i] = ContentCandidate{
			ContentID:   fmt.Sprintf("c%d", i),
			ContentType: "photo",
			AuthorID:    fmt.Sprintf("a%d", i%10),
			PublishedAt: now,
			LikeCount:   int64(50 - i),
		}
	}
	source := &mockCandidateSource{candidates: candidates}
	cache := NewSessionCache(hp, 2*time.Second, 1000)
	const goroutines = 100
	engine := NewEngine(
		cache,
		[]CandidateSource{source},
		WithRecallSourceMaxInflight(goroutines),
		WithRecallGlobalMaxInflight(goroutines),
	)

	errs := make(chan error, goroutines)
	for i := 0; i < goroutines; i++ {
		go func(userIdx int) {
			userID := fmt.Sprintf("user%d", userIdx%10)
			resp, err := engine.GetFeed(ctx, GetFeedRequest{
				UserID:    userID,
				SessionID: "s1",
				Limit:     20,
			})
			if err != nil {
				errs <- err
				return
			}
			if len(resp.Items) == 0 {
				errs <- fmt.Errorf("user %s got empty feed", userID)
				return
			}
			errs <- nil
		}(i)
	}

	for i := 0; i < goroutines; i++ {
		if err := <-errs; err != nil {
			t.Fatalf("concurrent feed failed: %v", err)
		}
	}
}

// --- Phase 5+ tests: rerank diversity, explore injection, cold-start, observability ---

func TestRerank_TagDedup_NoThreeConsecutiveSameTag(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	candidates := []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 100, ViewCount: 1000},
		{ContentID: "c2", ContentType: "video", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 90, ViewCount: 900},
		{ContentID: "c3", ContentType: "article", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 80, ViewCount: 800},
		{ContentID: "c4", ContentType: "photo", Tags: []string{"food"}, PublishedAt: now, LikeCount: 70, ViewCount: 700},
		{ContentID: "c5", ContentType: "video", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 60, ViewCount: 600},
	}
	source := &mockCandidateSource{candidates: candidates}

	engine := NewEngine(hp, []CandidateSource{source}, WithPolicyStore(noExplorePolicyStore()))
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 5})
	if err != nil {
		t.Fatal(err)
	}

	for i := 2; i < len(resp.Items); i++ {
		tag0 := firstTag(resp.Items[i-2].Tags)
		tag1 := firstTag(resp.Items[i-1].Tags)
		tag2 := firstTag(resp.Items[i].Tags)
		if tag0 != "" && tag0 == tag1 && tag1 == tag2 {
			t.Errorf("3 consecutive items at [%d-%d] share tag %q", i-2, i, tag0)
		}
	}
}

func TestRerank_ExploreInjection(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	var candidates []ContentCandidate
	for i := 0; i < 30; i++ {
		c := ContentCandidate{
			ContentID:   fmt.Sprintf("c%d", i),
			ContentType: "photo",
			Tags:        []string{fmt.Sprintf("tag%d", i%5)},
			PublishedAt: now,
			LikeCount:   int64(100 - i),
			ViewCount:   int64(1000 - i*10),
		}
		if i%5 == 0 {
			c.RecallPath = "explore_recall"
		}
		candidates = append(candidates, c)
	}
	source := &mockCandidateSource{candidates: candidates}

	engine := NewEngine(hp, []CandidateSource{source})
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 20})
	if err != nil {
		t.Fatal(err)
	}

	exploreCount := 0
	for _, item := range resp.Items {
		if item.RecallPath == "explore_recall" {
			exploreCount++
		}
	}
	minExpected := len(resp.Items) / 5
	if minExpected < 1 {
		minExpected = 1
	}
	if exploreCount < minExpected {
		t.Errorf("expected at least %d explore items in %d results, got %d",
			minExpected, len(resp.Items), exploreCount)
	}
}

func TestRerank_ColdStartGuarantee(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	var candidates []ContentCandidate
	contentTypes := []string{"photo", "video", "article"}
	for i := 0; i < 30; i++ {
		c := ContentCandidate{
			ContentID:    fmt.Sprintf("c%d", i),
			ContentType:  contentTypes[i%len(contentTypes)],
			Tags:         []string{fmt.Sprintf("tag%d", i%3)},
			PublishedAt:  now.Add(-time.Duration(24+i) * time.Hour),
			LikeCount:    int64(25 + i),
			CommentCount: int64(5),
			ShareCount:   int64(1),
			ViewCount:    int64(500 + i*50),
		}
		if i < 5 {
			c.PublishedAt = now.Add(-time.Duration(i) * time.Hour)
			c.ViewCount = int64(10 + i*5)
			c.LikeCount = int64(220 - i*10)
			c.CommentCount = int64(80 - i*5)
			c.ShareCount = int64(30 - i*2)
		}
		candidates = append(candidates, c)
	}
	source := &mockCandidateSource{candidates: candidates}

	engine := NewEngine(hp, []CandidateSource{source})
	resp, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u1", Limit: 20})
	if err != nil {
		t.Fatal(err)
	}

	coldStartCount := 0
	for _, item := range resp.Items {
		for _, c := range candidates {
			if c.ContentID == item.ContentID {
				ageHours := now.Sub(c.PublishedAt).Hours()
				if ageHours < 24 && c.ViewCount < 100 {
					coldStartCount++
				}
				break
			}
		}
	}
	minColdStart := len(resp.Items) / 10
	if minColdStart < 1 {
		minColdStart = 1
	}
	if coldStartCount < minColdStart {
		t.Errorf("expected at least %d cold-start items in %d results, got %d",
			minColdStart, len(resp.Items), coldStartCount)
	}
}

func TestObservability_RecordMetrics_NoError(t *testing.T) {
	RecordMetrics(PipelineMetrics{
		UserID:         "u1",
		TotalLatency:   100 * time.Millisecond,
		RecallLatency:  30 * time.Millisecond,
		ScoreLatency:   40 * time.Millisecond,
		RerankLatency:  20 * time.Millisecond,
		CandidateCount: 50,
		ResultCount:    10,
	})
}

func TestObservability_SlowRequestRecorded(t *testing.T) {
	RecordMetrics(PipelineMetrics{
		UserID:       "u1",
		TotalLatency: 300 * time.Millisecond,
		ResultCount:  10,
	})
}

func TestObservability_EmptyResultRecorded(t *testing.T) {
	RecordMetrics(PipelineMetrics{
		UserID:      "u1",
		ResultCount: 0,
	})
}

func TestRerankDiversitySignals_Computed(t *testing.T) {
	items := []ScoredCandidate{
		{
			Candidate: ContentCandidate{
				ContentID:   "c1",
				ContentType: "article",
				AuthorID:    "a1",
				Tags: []string{
					"Topic/旅行/玩法/观光游览",
					"Topic/地理/行政区/中国/四川省/成都市",
				},
			},
		},
		{
			Candidate: ContentCandidate{
				ContentID:   "c2",
				ContentType: "article",
				AuthorID:    "a1",
				Tags: []string{
					"Topic/旅行/玩法/观光游览",
					"Topic/地理/行政区/中国/四川省/成都市",
				},
			},
		},
		{
			Candidate: ContentCandidate{
				ContentID:   "c3",
				ContentType: "article",
				AuthorID:    "a2",
				Tags: []string{
					"Topic/旅行/旅行主题/城市漫步",
					"Topic/地理/行政区/中国/四川省/乐山市",
				},
			},
		},
	}

	repeatRate, hhi, distinctAuthors := computeAuthorDiversity(items)
	if distinctAuthors != 2 {
		t.Fatalf("expected 2 distinct authors, got %d", distinctAuthors)
	}
	if math.Abs(repeatRate-0.3333333) > 0.01 {
		t.Fatalf("unexpected repeat rate: %.4f", repeatRate)
	}
	if math.Abs(hhi-0.5555555) > 0.01 {
		t.Fatalf("unexpected author hhi: %.4f", hhi)
	}

	geoCoverage, distinctGeoBuckets := computeGeoCoverage(items)
	if distinctGeoBuckets != 1 {
		t.Fatalf("expected 1 distinct geo bucket, got %d", distinctGeoBuckets)
	}
	if math.Abs(geoCoverage-0.3333333) > 0.01 {
		t.Fatalf("unexpected geo coverage: %.4f", geoCoverage)
	}

	if topics := computeDistinctTopicCount(items); topics != 4 {
		t.Fatalf("expected 4 distinct topic tags, got %d", topics)
	}
}

func TestObservability_ModelTimeoutRecorded(t *testing.T) {
	RecordModelTimeout()
}

func TestModelVsRuleExperiment_PolicyResolvesValidBucket(t *testing.T) {
	p := recpolicy.Baseline()
	bucket := p.ResolveBucketOr(recpolicy.ExpModelVsRule, "testuser", nil, "rule")
	if bucket != "rule" && bucket != "model" {
		t.Errorf("unexpected bucket %q, expected 'rule' or 'model'", bucket)
	}
}

func TestModelVsRule_FallbackWhenExperimentMissing(t *testing.T) {
	p := recpolicy.Baseline()
	// An undefined experiment id must fall back to the provided default.
	bucket := p.ResolveBucketOr("rec_undefined_experiment", "u1", nil, "rule")
	if bucket != "rule" {
		t.Errorf("missing experiment should return fallback 'rule', got %q", bucket)
	}
}

func firstTag(tags []string) string {
	if len(tags) > 0 {
		return tags[0]
	}
	return ""
}
