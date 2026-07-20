package application

import (
	"context"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

// fakeProactiveInterestReader is a deterministic in-memory ProactiveInterestReader.
type fakeProactiveInterestReader struct {
	profile *ProactiveInterestProfile
	err     error
	calls   int
}

func (f *fakeProactiveInterestReader) GetInterestProfile(ctx context.Context, userID string) (*ProactiveInterestProfile, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.profile, nil
}

func travelSubscription() assistant.SkillSubscription {
	return assistant.SkillSubscription{
		SkillID: SkillTravelJourneyManager,
		Owner:   assistant.SkillSubscriptionOwner{OwnerType: "user", OwnerID: "user_travel"},
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			RawText: "今天出发前提醒",
			Queries: []string{"杭州 西湖 天气"},
		},
	}
}

func TestBuildP0ProactiveSkillResult_NilProfileIsBaseline(t *testing.T) {
	now := time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC)
	got := BuildP0ProactiveSkillResult(travelSubscription(), nil, now)

	if got.Personalized {
		t.Fatalf("nil profile must not personalize: %+v", got)
	}
	if got.Title != "出行管家：今日行程提醒" {
		t.Fatalf("baseline title changed: %q", got.Title)
	}
	if len(got.InterestTags) != 0 || len(got.MatchedSegments) != 0 || got.LifecycleStage != "" {
		t.Fatalf("nil profile must leave attribution empty: %+v", got)
	}
	if strings.Contains(got.Prompt, "用户兴趣画像") {
		t.Fatalf("nil profile must not inject profile context into prompt: %q", got.Prompt)
	}
}

func TestBuildP0ProactiveSkillResult_EmptyProfileIsBaseline(t *testing.T) {
	now := time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC)
	// A profile with no tags/segments/lifecycle (the user-service "new" empty
	// profile minus lifecycle) must not flip personalization on.
	got := BuildP0ProactiveSkillResult(travelSubscription(), &ProactiveInterestProfile{}, now)
	if got.Personalized {
		t.Fatalf("empty profile must not personalize: %+v", got)
	}
}

func TestBuildP0ProactiveSkillResult_PersonalizesWithInterestsAndSegments(t *testing.T) {
	now := time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC)
	profile := &ProactiveInterestProfile{
		TopInterests: []ProactiveInterest{
			{TagRef: "川西自驾", Dimension: "topic", Score: 0.91, Level: 4},
			{TagRef: "高原摄影", Dimension: "topic", Score: 0.72, Level: 3},
			{TagRef: "露营", Dimension: "activity", Score: 0.55, Level: 2},
			{TagRef: "应当被截断", Dimension: "topic", Score: 0.1, Level: 1},
		},
		LifecycleStage: "active",
		Segments:       []string{"travel_enthusiast"},
	}
	got := BuildP0ProactiveSkillResult(travelSubscription(), profile, now)

	if !got.Personalized {
		t.Fatalf("expected personalized result")
	}
	if got.LifecycleStage != "active" {
		t.Fatalf("lifecycle=%q want active", got.LifecycleStage)
	}
	if len(got.InterestTags) != 3 {
		t.Fatalf("interest tags should be capped at 3: %v", got.InterestTags)
	}
	if got.InterestTags[0] != "川西自驾" {
		t.Fatalf("interest tags priority order wrong: %v", got.InterestTags)
	}
	if len(got.MatchedSegments) != 1 || got.MatchedSegments[0] != "travel_enthusiast" {
		t.Fatalf("segments=%v", got.MatchedSegments)
	}
	// Why carries the interest attribution; Prompt carries explicit profile
	// context for the downstream model.
	if !strings.Contains(got.Why, "川西自驾") {
		t.Fatalf("why missing interest tag: %q", got.Why)
	}
	if !strings.Contains(got.Prompt, "用户兴趣画像") || !strings.Contains(got.Prompt, "travel_enthusiast") {
		t.Fatalf("prompt missing profile context: %q", got.Prompt)
	}
	// Baseline copy preserved (additive personalization).
	if !strings.Contains(got.Summary, "天气") {
		t.Fatalf("baseline summary lost: %q", got.Summary)
	}
}

func TestBuildP0ProactiveSkillResult_DormantLeadIn(t *testing.T) {
	now := time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC)
	profile := &ProactiveInterestProfile{
		TopInterests:   []ProactiveInterest{{TagRef: "登山", Dimension: "activity", Score: 0.6, Level: 3}},
		LifecycleStage: "dormant",
	}
	got := BuildP0ProactiveSkillResult(travelSubscription(), profile, now)
	if !strings.HasPrefix(got.Summary, "好久不见") {
		t.Fatalf("dormant lead-in missing: %q", got.Summary)
	}
}

// TestTickSkillSubscriptionCron_PersonalizesFromReader proves the end-to-end
// wiring: the cron tick path loads the profile via the injected reader and the
// resulting app message reflects personalization.
func TestTickSkillSubscriptionCron_PersonalizesFromReader(t *testing.T) {
	reader := &fakeProactiveInterestReader{profile: &ProactiveInterestProfile{
		TopInterests:   []ProactiveInterest{{TagRef: "川西自驾", Dimension: "topic", Score: 0.9, Level: 4}},
		LifecycleStage: "dormant",
		Segments:       []string{"travel_enthusiast"},
	}}
	notifications := newRecordingNotificationCommandWriter()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithNotificationAppMessageCommandWriter(notifications),
		WithProactiveInterestReader(reader),
	)
	service.now = func() time.Time { return time.Date(2026, 4, 29, 7, 0, 0, 0, time.UTC) }

	if _, err := service.CreateSkillSubscription(context.Background(), "user_travel", assistant.CreateSkillSubscriptionInput{
		SkillID:  SkillTravelJourneyManager,
		DomainID: "travel",
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			RawText: "出发前提醒行程",
			Queries: []string{"杭州 西湖 天气"},
		},
		Trigger: assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 7 * * *"},
	}); err != nil {
		t.Fatalf("CreateSkillSubscription error: %v", err)
	}

	if _, err := service.TickSkillSubscriptionCron(context.Background(), assistant.SkillSubscriptionCronTickInput{Now: "2026-04-29T07:00:00Z"}); err != nil {
		t.Fatalf("TickSkillSubscriptionCron error: %v", err)
	}
	if reader.calls == 0 {
		t.Fatalf("reader was not consulted on proactive tick")
	}
	messages := notifications.CommandsForUser("user_travel")
	if len(messages) != 1 {
		t.Fatalf("notification commands=%d, want 1", len(messages))
	}
	if !strings.HasPrefix(messages[0].Summary, "好久不见") {
		t.Fatalf("personalized dormant lead-in not reflected in message: %q", messages[0].Summary)
	}
	if !messages[0].Provenance.Personalized || messages[0].Provenance.LifecycleStage != "dormant" {
		t.Fatalf("notification provenance was not preserved: %+v", messages[0].Provenance)
	}
}

// TestTickSkillSubscriptionCron_ReaderErrorDegrades proves a reader failure does
// not block the proactive message (best-effort degradation).
func TestTickSkillSubscriptionCron_ReaderErrorDegrades(t *testing.T) {
	reader := &fakeProactiveInterestReader{err: context.DeadlineExceeded}
	notifications := newRecordingNotificationCommandWriter()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithNotificationAppMessageCommandWriter(notifications),
		WithProactiveInterestReader(reader),
	)
	service.now = func() time.Time { return time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC) }

	if _, err := service.CreateSkillSubscription(context.Background(), "user_news", assistant.CreateSkillSubscriptionInput{
		SkillID:         SkillNewsBriefing,
		DomainID:        "content",
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{RawText: "科技新闻", Queries: []string{"科技新闻"}},
		Trigger:         assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 8 * * *"},
	}); err != nil {
		t.Fatalf("CreateSkillSubscription error: %v", err)
	}

	result, err := service.TickSkillSubscriptionCron(context.Background(), assistant.SkillSubscriptionCronTickInput{Now: "2026-04-29T08:00:00Z"})
	if err != nil {
		t.Fatalf("reader error must not fail tick: %v", err)
	}
	if result.ProcessedCount != 1 {
		t.Fatalf("processed=%d, want 1 despite reader error", result.ProcessedCount)
	}
	messages := notifications.CommandsForUser("user_news")
	if len(messages) != 1 {
		t.Fatalf("notification commands=%d, want 1", len(messages))
	}
}
