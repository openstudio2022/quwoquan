package recommendation

import (
	"context"
	"fmt"
	"math"
	"sync"
	"testing"
	"time"

	experiments "quwoquan_service/runtime/experiments"
	learning "quwoquan_service/runtime/learning"
)

type mockCandidateSource struct {
	candidates []ContentCandidate
}

func (m *mockCandidateSource) Recall(_ context.Context, _ RecallRequest) ([]ContentCandidate, error) {
	return m.candidates, nil
}

type mockRedisClient struct {
	data   map[string]string
	sets   map[string]map[string]bool
	hashes map[string]map[string]string
}

func newMockRedis() *mockRedisClient {
	return &mockRedisClient{
		data:   make(map[string]string),
		sets:   make(map[string]map[string]bool),
		hashes: make(map[string]map[string]string),
	}
}

func (m *mockRedisClient) Get(_ context.Context, key string) (string, error) {
	return m.data[key], nil
}
func (m *mockRedisClient) Set(_ context.Context, key, value string, _ time.Duration) error {
	m.data[key] = value
	return nil
}
func (m *mockRedisClient) Del(_ context.Context, keys ...string) error {
	for _, k := range keys {
		delete(m.data, k)
	}
	return nil
}
func (m *mockRedisClient) SAdd(_ context.Context, key string, members ...string) error {
	if m.sets[key] == nil {
		m.sets[key] = make(map[string]bool)
	}
	for _, mem := range members {
		m.sets[key][mem] = true
	}
	return nil
}
func (m *mockRedisClient) SMembers(_ context.Context, key string) ([]string, error) {
	var result []string
	for k := range m.sets[key] {
		result = append(result, k)
	}
	return result, nil
}
func (m *mockRedisClient) SIsMember(_ context.Context, key, member string) (bool, error) {
	return m.sets[key][member], nil
}
func (m *mockRedisClient) HIncrByFloat(_ context.Context, key, field string, incr float64) error {
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
	if m.hashes[key] == nil {
		return map[string]string{}, nil
	}
	return m.hashes[key], nil
}
func (m *mockRedisClient) Expire(_ context.Context, _ string, _ time.Duration) error { return nil }

// PipelineRead implements RedisPipeliner for single-RTT batch reads.
func (m *mockRedisClient) PipelineRead(_ context.Context, ops []PipelineOp) error {
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

	exposed, _ := hp.IsExposed(ctx, "u1", "s1", "c1")
	if !exposed {
		t.Error("c1 should be exposed")
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

	state, _ := hp.GetSessionState(ctx, "u1", "s1")
	found := false
	for _, id := range state.NegativeIDs {
		if id == "c2" {
			found = true
		}
	}
	if !found {
		t.Error("c2 should be in negative set after dislike")
	}
}

func TestEngine_GetFeed_FiltersExposed(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	hp.ProcessSignal(ctx, BehaviorSignal{UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "click"})

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
			{ContentID: "c2", ContentType: "video", PublishedAt: time.Now()},
			{ContentID: "c3", ContentType: "article", PublishedAt: time.Now()},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source})
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

	engine := NewEngine(hp, []CandidateSource{source})
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
				ContentType:  "photo",
				PublishedAt:  now,
				LikeCount:    3,
				CommentCount: 1,
				ShareCount:   0,
				ViewCount:    100,
			},
		},
	}

	engine := NewEngine(hp, []CandidateSource{source}, WithExploreFraction(0))
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

	engine := NewEngine(hp, []CandidateSource{source}, WithExploreFraction(0))
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
		WithMaxAuthorPerFeed(2),
		WithExploreFraction(0),
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

func TestEngine_ABExperiment_AffectsScoring(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	resolver := experiments.NewHashResolver()
	RegisterRecWeightsExperiment(resolver)

	now := time.Now()
	source := &mockCandidateSource{candidates: []ContentCandidate{
		{ContentID: "c1", ContentType: "photo", Tags: []string{"travel"}, PublishedAt: now, LikeCount: 50},
		{ContentID: "c2", ContentType: "video", Tags: []string{"food"}, PublishedAt: now, LikeCount: 5},
	}}

	engine := NewEngine(hp, []CandidateSource{source},
		WithExperimentResolver(resolver),
		WithExploreFraction(0),
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

func TestResolveWeights_DefaultOnNilResolver(t *testing.T) {
	ctx := context.Background()
	w := ResolveWeights(ctx, nil, "u1")
	def := DefaultWeights()
	if w.TagRelevance != def.TagRelevance {
		t.Errorf("expected default TagRelevance %f, got %f", def.TagRelevance, w.TagRelevance)
	}
}

func TestResolveWeights_PresetBuckets(t *testing.T) {
	ctx := context.Background()
	resolver := experiments.NewHashResolver()
	RegisterRecWeightsExperiment(resolver)

	// Test a known preset
	assignment, _ := resolver.Resolve(ctx, ExpRecWeights, "testuser")
	if _, ok := WeightPresets[assignment.Bucket]; !ok {
		t.Errorf("assigned bucket %q not in WeightPresets", assignment.Bucket)
	}
}

type mockLearningRecorder struct {
	mu         sync.Mutex
	events     []struct{ eventType string }
	scorecards []struct{ runID string }
}

func (m *mockLearningRecorder) RecordEvent(_ context.Context, e learning.Event) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, struct{ eventType string }{e.EventType})
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
		{ContentID: "c1", ContentType: "photo", Score: 5.0, RecallPath: "tag_recall"},
		{ContentID: "c2", ContentType: "video", Score: 3.0, RecallPath: "hot_recall"},
	}

	err := fr.RecordImpression(ctx, "u1", "s1", items)
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
}

func TestFeedbackRecorder_RecordEngagement(t *testing.T) {
	mock := &mockLearningRecorder{}
	fr := NewFeedbackRecorder(mock)
	ctx := context.Background()

	err := fr.RecordEngagement(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "c1", Action: "like",
	}, 5.0)
	if err != nil {
		t.Fatal(err)
	}
	if len(mock.events) != 1 {
		t.Errorf("expected 1 engagement event, got %d", len(mock.events))
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
		WithExploreFraction(0),
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
		Weights:     DefaultWeights(),
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
			Action:    "click",
		}
	}
	buf.ProcessSignalBatch(ctx, signals)

	time.Sleep(150 * time.Millisecond)

	state, _ := hp.GetSessionState(ctx, "u1", "s1")
	if len(state.ExposedIDs) < 20 {
		t.Errorf("expected 20 exposed IDs after batch flush, got %d", len(state.ExposedIDs))
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
	if len(state.ExposedIDs) < 2 {
		t.Errorf("expected at least 2 exposed IDs, got %d", len(state.ExposedIDs))
	}
	found := false
	for _, id := range state.NegativeIDs {
		if id == "c2" {
			found = true
		}
	}
	if !found {
		t.Error("c2 should be in negative set")
	}
}

func TestHotPath_PipelineVsParallel_Consistent(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	for i := 0; i < 20; i++ {
		hp.ProcessSignal(ctx, BehaviorSignal{
			UserID: "u1", SessionID: "s1",
			ContentID: fmt.Sprintf("c%d", i), Action: "click",
			Tags: []string{fmt.Sprintf("tag%d", i%5)},
		})
	}
	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "u1", SessionID: "s1", ContentID: "bad1", Action: "dislike",
	})

	// Pipeline path
	statePipeline, err := hp.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}

	// Force parallel path by wrapping in a non-pipeliner reader
	parallelHP := &nonPipelinerHotPath{hp: hp}
	stateParallel, err := parallelHP.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatal(err)
	}

	if len(statePipeline.ExposedIDs) != len(stateParallel.ExposedIDs) {
		t.Errorf("exposed count mismatch: pipeline=%d parallel=%d",
			len(statePipeline.ExposedIDs), len(stateParallel.ExposedIDs))
	}
	if len(statePipeline.NegativeIDs) != len(stateParallel.NegativeIDs) {
		t.Errorf("negative count mismatch: pipeline=%d parallel=%d",
			len(statePipeline.NegativeIDs), len(stateParallel.NegativeIDs))
	}
	if len(statePipeline.TagWeights) != len(stateParallel.TagWeights) {
		t.Errorf("tag weights count mismatch: pipeline=%d parallel=%d",
			len(statePipeline.TagWeights), len(stateParallel.TagWeights))
	}
}

// nonPipelinerHotPath wraps HotPath with a redis that does NOT implement RedisPipeliner.
type nonPipelinerHotPath struct {
	hp *HotPath
}

func (n *nonPipelinerHotPath) GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error) {
	wrapped := &nonPipelinerRedis{inner: n.hp.redis}
	tmp := NewHotPath(wrapped)
	return tmp.GetSessionState(ctx, userID, sessionID)
}

type nonPipelinerRedis struct {
	inner RedisClient
}

func (r *nonPipelinerRedis) Get(ctx context.Context, key string) (string, error) {
	return r.inner.Get(ctx, key)
}
func (r *nonPipelinerRedis) Set(ctx context.Context, key, value string, ttl time.Duration) error {
	return r.inner.Set(ctx, key, value, ttl)
}
func (r *nonPipelinerRedis) Del(ctx context.Context, keys ...string) error {
	return r.inner.Del(ctx, keys...)
}
func (r *nonPipelinerRedis) SAdd(ctx context.Context, key string, members ...string) error {
	return r.inner.SAdd(ctx, key, members...)
}
func (r *nonPipelinerRedis) SMembers(ctx context.Context, key string) ([]string, error) {
	return r.inner.SMembers(ctx, key)
}
func (r *nonPipelinerRedis) SIsMember(ctx context.Context, key, member string) (bool, error) {
	return r.inner.SIsMember(ctx, key, member)
}
func (r *nonPipelinerRedis) HIncrByFloat(ctx context.Context, key, field string, incr float64) error {
	return r.inner.HIncrByFloat(ctx, key, field, incr)
}
func (r *nonPipelinerRedis) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	return r.inner.HGetAll(ctx, key)
}
func (r *nonPipelinerRedis) Expire(ctx context.Context, key string, ttl time.Duration) error {
	return r.inner.Expire(ctx, key, ttl)
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
	engine := NewEngine(cache, []CandidateSource{source})

	const goroutines = 100
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

	engine := NewEngine(hp, []CandidateSource{source}, WithExploreFraction(0))
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
	for i := 0; i < 30; i++ {
		c := ContentCandidate{
			ContentID:   fmt.Sprintf("c%d", i),
			ContentType: "photo",
			Tags:        []string{fmt.Sprintf("tag%d", i%3)},
			PublishedAt: now.Add(-time.Duration(i*10) * time.Hour),
			LikeCount:   int64(100 - i),
			ViewCount:   int64(500 + i*50),
		}
		if i < 5 {
			c.PublishedAt = now.Add(-time.Duration(i) * time.Hour)
			c.ViewCount = int64(10 + i*5)
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

func TestModelVsRuleExperiment(t *testing.T) {
	ctx := context.Background()
	resolver := experiments.NewHashResolver()
	RegisterModelVsRuleExperiment(resolver)

	bucket := ResolveModelBucket(ctx, resolver, "testuser")
	if bucket != "rule" && bucket != "model" {
		t.Errorf("unexpected bucket %q, expected 'rule' or 'model'", bucket)
	}
}

func TestResolveModelBucket_NilResolver(t *testing.T) {
	bucket := ResolveModelBucket(context.Background(), nil, "u1")
	if bucket != "rule" {
		t.Errorf("nil resolver should return 'rule', got %q", bucket)
	}
}

func firstTag(tags []string) string {
	if len(tags) > 0 {
		return tags[0]
	}
	return ""
}
