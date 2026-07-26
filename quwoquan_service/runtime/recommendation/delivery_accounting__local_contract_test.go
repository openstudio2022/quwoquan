package recommendation

// N3-3 契约：served 记账口径 = 最终下发集。
//  1. DeferDeliveryAccounting 模式下 GetFeed 不写曝光记忆（装配层还会过滤）；
//  2. RecordDelivery 只把传入的最终下发集记入 served（后续 FilterCandidates
//     按此过滤）；
//  3. publishHour 与请求时间特征随评分请求下发（训练-在线同源）。

import (
	"context"
	"errors"
	"math"
	"testing"
	"time"

	runtimelearning "quwoquan_service/runtime/learning"
	"quwoquan_service/runtime/recpolicy"
)

func testImpressionTrainingSnapshot() *trainingFeatureSnapshot {
	return &trainingFeatureSnapshot{
		userFeatures: map[string]any{"totalEvents": 1},
		itemFeatures: map[string]any{"contentType": "article"},
		capturedAt:   time.Date(2026, 7, 21, 0, 0, 0, 0, time.UTC),
	}
}

func TestRuleScorerUsesUnifiedFeatureSnapshotTime(t *testing.T) {
	policy := recpolicy.Baseline()
	snapshotAt := time.Date(2026, 7, 20, 16, 45, 0, 0, time.UTC)
	scored, err := (&RuleScorer{}).ScoreBatch(
		context.Background(),
		&ScoringFeatures{
			FeatureSnapshotAt: snapshotAt,
			Weights:           policy.WeightPresets[policy.DefaultPreset],
			Scorer:            policy.Scorer,
		},
		[]ContentCandidate{{
			ContentID:   "rule_snapshot_time",
			PublishedAt: snapshotAt.Add(-24 * time.Hour),
		}},
	)
	if err != nil || len(scored) != 1 {
		t.Fatalf("RuleScorer snapshot setup: scored=%+v err=%v", scored, err)
	}
	want := math.Exp(-24 / policy.Scorer.FreshnessHalfLifeHours)
	if got := scored[0].Detail["freshness"]; math.Abs(got-want) > 1e-12 {
		t.Fatalf("freshness must use FeatureSnapshotAt: got=%v want=%v", got, want)
	}
}

func TestGetFeed_DeferDeliveryAccountingSkipsServedWrite(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "c1", ContentType: "photo", PublishedAt: time.Now()},
			{ContentID: "c2", ContentType: "video", PublishedAt: time.Now()},
		},
	}
	engine := NewEngine(hp, []CandidateSource{source},
		WithExposureGovernance(hp, hp),
		WithPolicyStore(noExplorePolicyStore()),
	)

	resp, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u_defer", SessionID: "s1", Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	if len(resp.Items) == 0 {
		t.Fatal("expected items")
	}

	// defer 模式下不得写 served：同一候选再次请求仍可返回。
	second, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u_defer", SessionID: "s1", Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("second GetFeed: %v", err)
	}
	if len(second.Items) != len(resp.Items) {
		t.Fatalf("defer mode must not record served: first=%d second=%d", len(resp.Items), len(second.Items))
	}

	// RecordDelivery 按最终下发集记账：只记第一项（模拟装配层丢弃另一项）。
	deliveredID := resp.Items[0].ContentID
	undeliveredID := "c1"
	if deliveredID == "c1" {
		undeliveredID = "c2"
	}
	if err := engine.RecordDelivery(
		ctx,
		"u_defer",
		"s1",
		resp.Attribution,
		resp.Items[:1],
	); err != nil {
		t.Fatalf("record final delivery: %v", err)
	}
	// RecordDelivery 的曝光写是异步（500ms 超时 goroutine），等待其落库。
	deadline := time.Now().Add(2 * time.Second)
	for {
		filtered, err := hp.FilterCandidates(ctx, "u_defer", source.candidates, time.Now())
		if err != nil {
			t.Fatalf("filter: %v", err)
		}
		got := map[string]bool{}
		for _, c := range filtered {
			got[c.ContentID] = true
		}
		if !got[deliveredID] && got[undeliveredID] {
			break // 最终下发项被 served 过滤、未下发项仍可见。
		}
		if time.Now().After(deadline) {
			t.Fatalf("served accounting by final delivery set not observed: %+v", filtered)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func TestRemoteModelScorer_CarriesOnlineTimeFeaturesAndReleaseIdentity(t *testing.T) {
	var captured *ModelPredictRequest
	client := predictCaptureClient{captured: &captured}
	scorer := NewRemoteModelScorer(client, "content_feed")

	publishedAt := time.Date(2026, 7, 20, 9, 30, 0, 0, time.UTC)
	scoredAt := time.Date(2026, 7, 20, 16, 45, 0, 0, time.UTC) // Monday
	scored, err := scorer.ScoreBatch(context.Background(), &ScoringFeatures{
		Session:           &SessionState{},
		FeatureSnapshotAt: scoredAt,
	}, []ContentCandidate{
		{ContentID: "c1", PublishedAt: publishedAt},
		{ContentID: "c2"}, // 发布时间缺失有明确的 publishHour/ageHours 缺失语义。
	})
	if err != nil {
		t.Fatalf("score: %v", err)
	}
	if captured == nil || len(captured.Candidates) != 2 {
		t.Fatalf("predict request not captured: %+v", captured)
	}
	if got := captured.Candidates[0].PublishHour; got != 9 {
		t.Fatalf("publishHour want 9 (UTC hour of publishedAt), got %d", got)
	}
	if got := captured.Candidates[1].PublishHour; got != -1 {
		t.Fatalf("missing publishedAt must map to publishHour -1, got %d", got)
	}
	if got := captured.Candidates[1].AgeHours; got != 0 {
		t.Fatalf("missing publishedAt must map to ageHours 0, got %v", got)
	}
	if got := captured.Context["requestHour"]; got != 16 {
		t.Fatalf("requestHour must use feature snapshot UTC hour, got %v", got)
	}
	if got := captured.Context["requestDayOfWeek"]; got != 0 {
		t.Fatalf("requestDayOfWeek must use Python Monday=0 semantics, got %v", got)
	}
	if len(scored) != 2 || scored[0].ModelReleaseID != "model_release_test_001" {
		t.Fatalf("model release identity must survive scoring response: %+v", scored)
	}
}

func TestRuleScorerTreatsMissingPublishedAtAsNeutralFreshness(t *testing.T) {
	scored, err := (&RuleScorer{}).ScoreBatch(context.Background(), &ScoringFeatures{
		FeatureSnapshotAt: time.Date(2026, 7, 20, 16, 45, 0, 0, time.UTC),
	}, []ContentCandidate{{ContentID: "missing_published_at"}})
	if err != nil {
		t.Fatalf("rule score: %v", err)
	}
	if len(scored) != 1 || scored[0].Detail["freshness"] != 1 {
		t.Fatalf("missing publishedAt freshness=%v, want 1", scored)
	}
}

func TestRemoteModelScorerRejectsUnattributedOrIncompleteResponses(t *testing.T) {
	candidates := []ContentCandidate{
		{ContentID: "c1", PublishedAt: time.Now().UTC()},
		{ContentID: "c2", PublishedAt: time.Now().UTC()},
	}
	tests := []struct {
		name     string
		response *ModelPredictResponse
	}{
		{
			name: "missing active release",
			response: &ModelPredictResponse{Scores: []CandidateScore{
				{ContentID: "c1", Score: 1},
				{ContentID: "c2", Score: 0.5},
			}},
		},
		{
			name: "partial scores",
			response: &ModelPredictResponse{
				ModelReleaseID: "release-1",
				Scores:         []CandidateScore{{ContentID: "c1", Score: 1}},
			},
		},
		{
			name: "unknown candidate",
			response: &ModelPredictResponse{
				ModelReleaseID: "release-1",
				Scores: []CandidateScore{
					{ContentID: "c1", Score: 1},
					{ContentID: "unknown", Score: 0.5},
				},
			},
		},
		{name: "nil response", response: nil},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			scorer := NewRemoteModelScorer(
				staticPredictResponseClient{response: testCase.response},
				"content_feed",
			)
			if _, err := scorer.ScoreBatch(
				context.Background(),
				&ScoringFeatures{Session: &SessionState{}},
				candidates,
			); err == nil {
				t.Fatal("invalid model response must trigger CascadeScorer fallback")
			}
		})
	}
}

func TestRecordDeliveryPersistsOnlineFeatureSnapshot(t *testing.T) {
	recorder := &snapshotLearningRecorder{events: make(chan runtimelearning.Event, 1)}
	userFeatures := &UserFeatureVector{
		TagAffinities:  map[string]float64{"Topic/旅行": 3.5, "Topic/无关": 99},
		TotalLikes:     7,
		EngagementRate: 0.25,
	}
	source := &mockCandidateSource{candidates: []ContentCandidate{{
		ContentID:    "snapshot_c1",
		ContentType:  "article",
		AuthorID:     "author_1",
		Tags:         []string{"Topic/旅行"},
		PublishedAt:  time.Now().UTC().Add(-24 * time.Hour),
		ViewCount:    12,
		CommentCount: 3,
		RecallPath:   "tag_recall",
		QualityScore: 0.8,
	}}}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{source},
		WithFeatureProvider(staticFeatureProvider{features: userFeatures}),
		WithFeedbackRecorder(NewFeedbackRecorder(recorder)),
		WithPolicyStore(noExplorePolicyStore()),
	)

	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "snapshot_user", PersonaID: "snapshot_persona",
		SessionID: "snapshot_session", Limit: 1,
		FeedRequestID: "snapshot_request", DeferDeliveryAccounting: true,
	})
	if err != nil || len(response.Items) != 1 {
		t.Fatalf("GetFeed snapshot setup: response=%+v err=%v", response, err)
	}

	// 快照必须在 GetFeed 在线评分时冻结；之后修改源对象不得污染训练事实。
	userFeatures.TotalLikes = 999
	source.candidates[0].ViewCount = 999
	if err := engine.RecordDelivery(
		context.Background(),
		"snapshot_user",
		"snapshot_session",
		response.Attribution,
		response.Items,
	); err != nil {
		t.Fatalf("record snapshot delivery: %v", err)
	}

	select {
	case event := <-recorder.events:
		if event.UserID != "snapshot_user" {
			t.Fatalf("impression actor=%q, want the recommendation actor", event.UserID)
		}
		if event.PersonaID != "snapshot_persona" {
			t.Fatalf("impression persona=%q, want snapshot_persona", event.PersonaID)
		}
		if got := event.Labels["contentType"]; got != "article" {
			t.Fatalf("impression target type=%q, want article", got)
		}
		if got := event.Context["feedRequestId"]; got != "snapshot_request" {
			t.Fatalf("impression request correlation=%v, want snapshot_request", got)
		}
		if got := event.Context["rank"]; got != 1 {
			t.Fatalf("impression server rank=%v, want 1", got)
		}
		userSnapshot, ok := event.Context["userFeatureSnapshot"].(map[string]any)
		if !ok {
			t.Fatalf("missing userFeatureSnapshot: %+v", event.Context)
		}
		if got := userSnapshot["totalLikes"]; got != 7 {
			t.Fatalf("user snapshot changed after scoring: got=%v want=7", got)
		}
		itemSnapshot, ok := event.Context["itemFeatureSnapshot"].(map[string]any)
		if !ok {
			t.Fatalf("missing itemFeatureSnapshot: %+v", event.Context)
		}
		if got := itemSnapshot["viewCount"]; got != int64(12) {
			t.Fatalf("item snapshot changed after scoring: got=%v want=12", got)
		}
		if got := itemSnapshot["recallPath"]; got != "tag_recall" {
			t.Fatalf("recallPath snapshot mismatch: %v", got)
		}
		snapshotAt, ok := event.Context["featureSnapshotAt"].(string)
		if !ok {
			t.Fatalf("featureSnapshotAt missing: %+v", event.Context)
		}
		parsedSnapshotAt, err := time.Parse(time.RFC3339Nano, snapshotAt)
		if err != nil {
			t.Fatalf("featureSnapshotAt must be RFC3339Nano: %v", err)
		}
		occurredAt, err := time.Parse(time.RFC3339Nano, event.OccurredAt)
		if err != nil {
			t.Fatalf("impression occurredAt must preserve RFC3339Nano precision: %v", err)
		}
		if occurredAt.Before(parsedSnapshotAt) {
			t.Fatalf(
				"impression occurredAt must not precede its online feature snapshot: occurred=%s snapshot=%s",
				occurredAt,
				parsedSnapshotAt,
			)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for immutable impression snapshot")
	}
}

func TestFeedbackRecorderDoesNotSwallowImpressionWriteFailure(t *testing.T) {
	recorder := NewFeedbackRecorder(failingLearningRecorder{})
	err := recorder.RecordImpression(
		context.Background(),
		"user-1",
		"session-1",
		ImpressionAttribution{FeedRequestID: "request-1"},
		[]FeedItem{{ContentID: "content-1", trainingFeatures: testImpressionTrainingSnapshot()}},
	)
	if err == nil {
		t.Fatal("learning sink failure must remain observable")
	}
}

func TestEngineRecordDeliveryPropagatesImpressionBufferFailure(t *testing.T) {
	engine := &Engine{feedback: NewFeedbackRecorder(failingLearningRecorder{})}
	err := engine.RecordDelivery(
		context.Background(),
		"delivery-user",
		"delivery-session",
		DeliveryAttribution{FeedRequestID: "delivery-request"},
		[]FeedItem{{
			ContentID:        "delivery-content",
			trainingFeatures: testImpressionTrainingSnapshot(),
		}},
	)
	if err == nil {
		t.Fatal("final delivery must fail when its learning fact cannot enter the buffer")
	}
}

func TestFeedbackRecorderRejectsMissingOnlineFeatureSnapshot(t *testing.T) {
	events := &snapshotLearningRecorder{events: make(chan runtimelearning.Event, 1)}
	recorder := NewFeedbackRecorder(events)
	err := recorder.RecordImpression(
		context.Background(),
		"snapshot-user",
		"snapshot-session",
		ImpressionAttribution{FeedRequestID: "snapshot-request"},
		[]FeedItem{{ContentID: "missing-snapshot"}},
	)
	if err == nil {
		t.Fatal("impression without an immutable online feature snapshot must fail closed")
	}
	select {
	case event := <-events.events:
		t.Fatalf("missing snapshot must not emit partial learning fact: %+v", event)
	default:
	}
}

func TestFeedbackRecorderRejectsLearningFactsWithoutFeedRequestID(t *testing.T) {
	events := &snapshotLearningRecorder{events: make(chan runtimelearning.Event, 2)}
	recorder := NewFeedbackRecorder(events)

	err := recorder.RecordImpression(
		context.Background(),
		"unattributed-user",
		"unattributed-session",
		ImpressionAttribution{},
		[]FeedItem{{
			ContentID:        "unattributed-content",
			trainingFeatures: testImpressionTrainingSnapshot(),
		}},
	)
	if err == nil {
		t.Fatal("impression without feedRequestId must fail closed")
	}
	err = recorder.RecordEngagement(context.Background(), BehaviorSignal{
		UserID: "unattributed-user", SessionID: "unattributed-session",
		ContentID: "unattributed-content", Action: "like",
	}, 0)
	if err == nil {
		t.Fatal("engagement without feedRequestId must fail closed")
	}
	select {
	case event := <-events.events:
		t.Fatalf("unattributed learning fact must not be emitted: %+v", event)
	default:
	}
}

func TestFeedbackRecorderPreservesVerifiedPersona(t *testing.T) {
	events := &snapshotLearningRecorder{events: make(chan runtimelearning.Event, 1)}
	recorder := NewFeedbackRecorder(events)
	if err := recorder.RecordEngagement(context.Background(), BehaviorSignal{
		UserID:        "recommendation_actor",
		PersonaID:     "verified_persona",
		SessionID:     "feedback_session",
		FeedRequestID: "feedback_request",
		ContentID:     "feedback_content",
		ContentType:   "article",
		Action:        "click",
	}, 0.5); err != nil {
		t.Fatalf("record engagement: %v", err)
	}
	select {
	case event := <-events.events:
		if event.UserID != "recommendation_actor" || event.PersonaID != "verified_persona" {
			t.Fatalf("feedback identity drifted: %+v", event)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for feedback fact")
	}
}

func TestEngine_ModelReleaseIdentityReachesImpressionFact(t *testing.T) {
	recorder := &snapshotLearningRecorder{events: make(chan runtimelearning.Event, 1)}
	policy := testPolicyStore(func(p *recpolicy.RecPolicy) {
		p.Scorer.ExploreFraction = 0
		for i := range p.Experiments {
			if p.Experiments[i].ID == recpolicy.ExpModelVsRule {
				p.Experiments[i].Enabled = true
				p.Experiments[i].Buckets = []recpolicy.ExperimentBucket{
					{Name: "model", WeightPct: 100},
					{Name: "rule", WeightPct: 0},
				}
			}
		}
	})
	source := &mockCandidateSource{candidates: []ContentCandidate{{
		ContentID: "release_c1", PublishedAt: time.Now().UTC(),
	}}}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{source},
		WithScorer(releaseIdentityScorer{releaseID: "model_release_20260720"}),
		WithFeedbackRecorder(NewFeedbackRecorder(recorder)),
		WithPolicyStore(policy),
	)

	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "release_user", SessionID: "release_session", Limit: 1,
		FeedRequestID: "release_request", DeferDeliveryAccounting: true,
	})
	if err != nil || len(response.Items) != 1 {
		t.Fatalf("GetFeed release attribution: response=%+v err=%v", response, err)
	}
	if response.Attribution.ModelReleaseID != "model_release_20260720" {
		t.Fatalf("delivery attribution lost model release: %+v", response.Attribution)
	}
	if err := engine.RecordDelivery(
		context.Background(),
		"release_user",
		"release_session",
		response.Attribution,
		response.Items,
	); err != nil {
		t.Fatalf("record release-attributed delivery: %v", err)
	}

	select {
	case event := <-recorder.events:
		if got := event.Context["modelReleaseId"]; got != "model_release_20260720" {
			t.Fatalf("impression fact lost model release identity: %v", got)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for model-attributed impression fact")
	}
}

type staticFeatureProvider struct {
	features *UserFeatureVector
}

func (p staticFeatureProvider) GetFeatures(context.Context, string) (*UserFeatureVector, error) {
	return p.features, nil
}

type snapshotLearningRecorder struct {
	events chan runtimelearning.Event
}

func (r *snapshotLearningRecorder) RecordEvent(
	_ context.Context,
	event runtimelearning.Event,
) error {
	r.events <- event
	return nil
}

func (*snapshotLearningRecorder) RecordScorecard(
	context.Context,
	runtimelearning.Scorecard,
) error {
	return nil
}

type failingLearningRecorder struct{}

func (failingLearningRecorder) RecordEvent(
	context.Context,
	runtimelearning.Event,
) error {
	return errors.New("learning sink unavailable")
}

func (failingLearningRecorder) RecordScorecard(
	context.Context,
	runtimelearning.Scorecard,
) error {
	return nil
}

type predictCaptureClient struct {
	captured **ModelPredictRequest
}

func (c predictCaptureClient) Predict(_ context.Context, req *ModelPredictRequest) (*ModelPredictResponse, error) {
	*c.captured = req
	scores := make([]CandidateScore, len(req.Candidates))
	for i, cand := range req.Candidates {
		scores[i] = CandidateScore{ContentID: cand.ContentID, Score: 0.5}
	}
	return &ModelPredictResponse{
		Scores:         scores,
		ModelReleaseID: "model_release_test_001",
	}, nil
}

type staticPredictResponseClient struct {
	response *ModelPredictResponse
}

func (c staticPredictResponseClient) Predict(
	context.Context,
	*ModelPredictRequest,
) (*ModelPredictResponse, error) {
	return c.response, nil
}

type releaseIdentityScorer struct {
	releaseID string
}

func (s releaseIdentityScorer) ScoreBatch(
	_ context.Context,
	_ *ScoringFeatures,
	candidates []ContentCandidate,
) ([]ScoredCandidate, error) {
	scored := make([]ScoredCandidate, 0, len(candidates))
	for _, candidate := range candidates {
		scored = append(scored, ScoredCandidate{
			Candidate:      candidate,
			Score:          1,
			ModelReleaseID: s.releaseID,
		})
	}
	return scored, nil
}

// 防回归：非 defer 调用方（若未来出现）仍在 GetFeed 内联记账，语义不变。
func TestGetFeed_InlineAccountingStillRecordsServed(t *testing.T) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	source := &mockCandidateSource{
		candidates: []ContentCandidate{
			{ContentID: "inline_c1", ContentType: "photo", PublishedAt: time.Now()},
		},
	}
	engine := NewEngine(hp, []CandidateSource{source},
		WithExposureGovernance(hp, hp),
		WithPolicyStore(testPolicyStore(func(p *recpolicy.RecPolicy) {
			p.Scorer.ExploreFraction = 0
		})),
	)
	if _, err := engine.GetFeed(ctx, GetFeedRequest{UserID: "u_inline", SessionID: "s1", Limit: 10}); err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for {
		filtered, err := hp.FilterCandidates(ctx, "u_inline", source.candidates, time.Now())
		if err != nil {
			t.Fatalf("filter: %v", err)
		}
		if len(filtered) == 0 {
			break // inline 模式已记 served
		}
		if time.Now().After(deadline) {
			t.Fatal("inline accounting must record served")
		}
		time.Sleep(20 * time.Millisecond)
	}
}
