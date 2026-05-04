package application

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/projection"
)

func TestReportInteractionEvents_DerivesFeedbackAndDedups(t *testing.T) {
	store := persistence.NewMemoryEventStore()
	cache := rtredis.NewMemoryClient()
	service := NewAssistantService(store, persistence.NewMemoryConsentStore(), cache)
	now := time.Date(2026, 4, 1, 10, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }

	event := assistant.InteractionEvent{
		EventID:             "evt_1",
		RunID:               "run_1",
		UserID:              "user_1",
		SessionID:           "session_1",
		PageType:            "assistant_dialog",
		DomainID:            "general",
		ExplicitThumb:       "down",
		ExplicitReasonCodes: []string{"unsafe", "unsafe", "privacy"},
		CorrectionText:      "需要更准确的回答",
	}

	resp, err := service.ReportInteractionEvents(context.Background(), []assistant.InteractionEvent{event, event})
	if err != nil {
		t.Fatalf("ReportInteractionEvents error: %v", err)
	}
	if got := resp["acceptedCount"]; got != 2 {
		t.Fatalf("acceptedCount=%v, want 2", got)
	}
	if got := resp["resource"]; got != "interaction_event_batch" {
		t.Fatalf("resource=%v", got)
	}
	items, err := store.ListLatestInteractionEvents(context.Background(), "user_1", 10)
	if err != nil {
		t.Fatalf("ListLatestInteractionEvents error: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("stored events=%d, want 1 after dedup", len(items))
	}
	stored := items[0]
	if stored.EventType != "feedback" {
		t.Fatalf("eventType=%q, want feedback", stored.EventType)
	}
	if stored.FeedbackType != "thumbs_down" {
		t.Fatalf("feedbackType=%q, want thumbs_down", stored.FeedbackType)
	}
	if stored.FeedbackScore != -1 {
		t.Fatalf("feedbackScore=%v, want -1", stored.FeedbackScore)
	}
	if len(stored.ExplicitReasonCodes) != 2 {
		t.Fatalf("explicitReasonCodes=%v, want deduped 2 items", stored.ExplicitReasonCodes)
	}
	cached, err := cache.HGetAll(context.Background(), "assistant:learning:event:user_1:evt_1")
	if err != nil {
		t.Fatalf("HGetAll hot path error: %v", err)
	}
	if cached["priority"] != "high" {
		t.Fatalf("priority=%q, want high", cached["priority"])
	}
	if cached["queryTextDigest"] != "" {
		t.Fatalf("queryTextDigest=%q, want empty", cached["queryTextDigest"])
	}
}

func TestListSkillsIncludesP0CloudManagedSkills(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
	)

	view, err := service.ListSkills(context.Background(), "user_1", 64)
	if err != nil {
		t.Fatalf("ListSkills error: %v", err)
	}
	seen := map[string]bool{}
	for _, item := range view.Items {
		seen[item.SkillID] = true
	}
	for _, skillID := range []string{
		"weather",
		"finance_consumer",
		"travel_planning",
		SkillDailyAssistant,
		SkillNewsBriefing,
		SkillStockSentinel,
		SkillTravelJourneyManager,
	} {
		if !seen[skillID] {
			t.Fatalf("missing P0 skill %q in catalog: %#v", skillID, view.Items)
		}
	}
}

func TestDefaultSkillRuntimeRoutesDomainSkills(t *testing.T) {
	cases := []struct {
		name  string
		text  string
		skill string
	}{
		{name: "weather", text: "深圳明天天气怎么样，穿什么衣服？", skill: "weather"},
		{name: "finance", text: "今天 A 股和比亚迪有哪些重大消息？", skill: "finance_consumer"},
		{name: "travel", text: "明天杭州一日游，结合天气路况和景点拥堵规划一下", skill: "travel_planning"},
		{name: "fortune", text: "帮我看看金牛座这周事业和感情运势，轻松娱乐就好。", skill: "fortune_astrology"},
		{name: "astrology", text: "帮我解释上升星座和太阳星座有什么区别。", skill: "astrology_constellation"},
		{name: "fallback", text: "帮我搜索并总结最近有哪些值得关注的 AI 产品发布。", skill: "fallback_general_search"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			selection, err := DefaultSkillRuntime{}.SelectSkill(context.Background(), assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: tc.text},
			})
			if err != nil {
				t.Fatalf("SelectSkill error: %v", err)
			}
			if selection.SkillID != tc.skill {
				t.Fatalf("skillID=%q, want %q", selection.SkillID, tc.skill)
			}
			if len(selection.ToolPolicy) == 0 {
				t.Fatalf("empty tool policy: %#v", selection)
			}
		})
	}
}

type recordingSkillSelectionModel struct {
	called bool
}

func (p *recordingSkillSelectionModel) Complete(context.Context, ModelRequest) (ModelResponse, error) {
	p.called = true
	return ModelResponse{Text: `{"skillId":"fallback_general_search"}`}, nil
}

func TestModelDrivenSkillRuntimeUsesManifestHintBeforeModel(t *testing.T) {
	model := &recordingSkillSelectionModel{}
	selection, err := ModelDrivenSkillRuntime{Model: model}.SelectSkill(context.Background(), assistant.AssistantTurn{
		TurnID: "atn_manifest_hint",
		Input:  assistant.AssistantTurnInput{Text: "shenzhen tian qi"},
	})
	if err != nil {
		t.Fatalf("SelectSkill error: %v", err)
	}
	if selection.SkillID != "weather" {
		t.Fatalf("skillID=%q, want weather", selection.SkillID)
	}
	if model.called {
		t.Fatal("model skill selection should be skipped when manifest hint is enough")
	}
}

func TestReportScorecards_DedupsAndWritesAggregateHotPath(t *testing.T) {
	store := persistence.NewMemoryEventStore()
	cache := rtredis.NewMemoryClient()
	service := NewAssistantService(store, persistence.NewMemoryConsentStore(), cache)
	now := time.Date(2026, 4, 1, 11, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }

	score := assistant.Scorecard{
		ScoreID:     "score_1",
		EventID:     "evt_1",
		RunID:       "run_1",
		UserID:      "user_1",
		DomainID:    "assistant",
		MetricID:    "safety_compliance",
		ScoreValue:  1.8,
		ScoreSource: "hybrid",
	}

	resp, err := service.ReportScorecards(context.Background(), []assistant.Scorecard{score, score})
	if err != nil {
		t.Fatalf("ReportScorecards error: %v", err)
	}
	if got := resp["acceptedCount"]; got != 2 {
		t.Fatalf("acceptedCount=%v, want 2", got)
	}
	items, err := store.ListLatestScorecards(context.Background(), "user_1", 10)
	if err != nil {
		t.Fatalf("ListLatestScorecards error: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("stored scorecards=%d, want 1 after dedup", len(items))
	}
	cached, err := cache.HGetAll(context.Background(), "rec:assistant_score:user_1:safety_compliance")
	if err != nil {
		t.Fatalf("HGetAll score hot path error: %v", err)
	}
	if cached["priority"] != "high" {
		t.Fatalf("priority=%q, want high", cached["priority"])
	}
	if cached["sampleCount"] != "1" {
		t.Fatalf("sampleCount=%q, want 1", cached["sampleCount"])
	}
	if cached["scoreValue"] != "1.8" {
		t.Fatalf("scoreValue=%q, want 1.8", cached["scoreValue"])
	}
}

func TestReportScorecards_RejectsOutOfRangeScore(t *testing.T) {
	service := NewAssistantService(persistence.NewMemoryEventStore(), persistence.NewMemoryConsentStore(), rtredis.NewMemoryClient())
	_, err := service.ReportScorecards(context.Background(), []assistant.Scorecard{{
		ScoreID:    "score_bad",
		EventID:    "evt_1",
		UserID:     "user_1",
		MetricID:   "answer_relevance",
		ScoreValue: 5.5,
	}})
	if err == nil {
		t.Fatal("expected error for out-of-range scoreValue")
	}
}

func TestGetLearningOpsSummary_UsesProjectedProfile(t *testing.T) {
	store := persistence.NewMemoryEventStore()
	profiles := projection.NewMemoryLearningProfileStore()
	cache := rtredis.NewMemoryClient()
	service := NewAssistantService(
		store,
		persistence.NewMemoryConsentStore(),
		cache,
		WithLearningProfileStore(profiles),
	)
	now := time.Date(2026, 4, 1, 12, 0, 0, 0, time.UTC)
	_, err := service.ReportInteractionEvents(context.Background(), []assistant.InteractionEvent{{
		EventID:             "evt_ops_1",
		RunID:               "run_ops_1",
		UserID:              "user_ops_1",
		SessionID:           "session_ops_1",
		PageType:            "assistant_dialog",
		DomainID:            "assistant",
		ExplicitThumb:       "down",
		CorrectionText:      "需要更准确",
		CreatedAt:           now,
		FeedbackType:        "thumbs_down",
		FeedbackScore:       -1,
		EventType:           "feedback",
		ExplicitReasonCodes: []string{"unsafe", "privacy"},
	}})
	if err != nil {
		t.Fatalf("ReportInteractionEvents error: %v", err)
	}
	_, err = service.ReportScorecards(context.Background(), []assistant.Scorecard{{
		ScoreID:     "score_ops_1",
		EventID:     "evt_ops_1",
		RunID:       "run_ops_1",
		UserID:      "user_ops_1",
		DomainID:    "assistant",
		MetricID:    "answer_relevance",
		ScoreValue:  2.0,
		ScoreSource: "hybrid",
		CreatedAt:   now,
	}})
	if err != nil {
		t.Fatalf("ReportScorecards error: %v", err)
	}
	summary, err := service.GetLearningOpsSummary(context.Background(), "user_ops_1")
	if err != nil {
		t.Fatalf("GetLearningOpsSummary error: %v", err)
	}
	if summary.UserID != "user_ops_1" {
		t.Fatalf("userID=%q", summary.UserID)
	}
	if summary.NegativeFeedbackCount != 1 {
		t.Fatalf("negativeFeedbackCount=%d, want 1", summary.NegativeFeedbackCount)
	}
	if summary.LastMetricID != "answer_relevance" {
		t.Fatalf("lastMetricId=%q", summary.LastMetricID)
	}
	if summary.MetricAverages["answer_relevance"] != 2.0 {
		t.Fatalf("metric average=%v, want 2.0", summary.MetricAverages["answer_relevance"])
	}
	if len(summary.TopReasonCodes) == 0 || summary.TopReasonCodes[0] != "privacy" && summary.TopReasonCodes[0] != "unsafe" {
		t.Fatalf("topReasonCodes=%v", summary.TopReasonCodes)
	}
}
