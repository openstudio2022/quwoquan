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

func TestSkillSubscriptionLifecycle(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
	)
	service.now = func() time.Time { return time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC) }

	created, err := service.CreateSkillSubscription(context.Background(), "user_1", assistant.CreateSkillSubscriptionInput{
		SkillID:  "news_briefing",
		DomainID: "content",
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			RawText: "每天早上 8 点给我科技新闻摘要",
		},
		Trigger: assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 8 * * *"},
	})
	if err != nil {
		t.Fatalf("CreateSkillSubscription error: %v", err)
	}
	if created.SubscriptionID == "" || created.Status != assistant.SkillSubscriptionStatusActive {
		t.Fatalf("created subscription=%+v", created)
	}
	if created.Destination.DestinationType != "user" || created.Destination.DestinationID != "user_1" {
		t.Fatalf("destination=%+v", created.Destination)
	}

	list, err := service.ListSkillSubscriptions(context.Background(), "user_1", "", 20)
	if err != nil {
		t.Fatalf("ListSkillSubscriptions error: %v", err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("items=%d, want 1", len(list.Items))
	}

	paused, err := service.UpdateSkillSubscriptionStatus(context.Background(), "user_1", created.SubscriptionID, assistant.UpdateSkillSubscriptionStatusInput{
		Status: assistant.SkillSubscriptionStatusPaused,
	})
	if err != nil {
		t.Fatalf("UpdateSkillSubscriptionStatus error: %v", err)
	}
	if paused.Status != assistant.SkillSubscriptionStatusPaused {
		t.Fatalf("status=%q, want paused", paused.Status)
	}
}

func TestUpsertSkillSubscriptionIsIdempotent(t *testing.T) {
	store := persistence.NewMemorySkillSubscriptionStore()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(store),
	)
	now := time.Date(2026, 7, 13, 0, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }
	input := assistant.UpsertSkillSubscriptionInput{
		SubscriptionID: "sub_environment_seed",
		SkillID:        "stock_sentinel",
		DomainID:       "finance",
		Status:         assistant.SkillSubscriptionStatusActive,
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			RawText: "environment seed: stock_sentinel",
			Queries: []string{"stock_sentinel"},
		},
		Trigger: assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 8 * * *"},
	}
	first, err := service.UpsertSkillSubscription(context.Background(), "user_seed", input)
	if err != nil {
		t.Fatalf("first UpsertSkillSubscription error: %v", err)
	}
	now = now.Add(time.Hour)
	input.Status = assistant.SkillSubscriptionStatusPaused
	second, err := service.UpsertSkillSubscription(context.Background(), "user_seed", input)
	if err != nil {
		t.Fatalf("second UpsertSkillSubscription error: %v", err)
	}
	if second.SubscriptionID != first.SubscriptionID {
		t.Fatalf("subscription id changed: first=%q second=%q", first.SubscriptionID, second.SubscriptionID)
	}
	if !second.CreatedAt.Equal(first.CreatedAt) {
		t.Fatalf("createdAt changed: first=%s second=%s", first.CreatedAt, second.CreatedAt)
	}
	if second.Status != assistant.SkillSubscriptionStatusPaused {
		t.Fatalf("status=%q, want paused", second.Status)
	}
	list, err := service.ListSkillSubscriptions(context.Background(), "user_seed", "", 20)
	if err != nil {
		t.Fatalf("ListSkillSubscriptions error: %v", err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("items=%d, want one idempotently upserted subscription", len(list.Items))
	}
}

func TestTickSkillSubscriptionCronCreatesProactiveTurnAndAppMessage(t *testing.T) {
	notifications := newRecordingNotificationCommandWriter()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithNotificationAppMessageCommandWriter(notifications),
	)
	service.now = func() time.Time { return time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC) }

	_, err := service.CreateSkillSubscription(context.Background(), "user_1", assistant.CreateSkillSubscriptionInput{
		SkillID:  "news_briefing",
		DomainID: "content",
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			RawText: "每天早上 8 点给我科技新闻摘要",
			Queries: []string{"科技新闻"},
		},
		Trigger: assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 8 * * *"},
	})
	if err != nil {
		t.Fatalf("CreateSkillSubscription error: %v", err)
	}

	result, err := service.TickSkillSubscriptionCron(context.Background(), assistant.SkillSubscriptionCronTickInput{
		Now: "2026-04-29T08:00:00Z",
	})
	if err != nil {
		t.Fatalf("TickSkillSubscriptionCron error: %v", err)
	}
	if result.ProcessedCount != 1 || len(result.CreatedTurnIDs) != 1 || len(result.CreatedMessageIDs) != 1 {
		t.Fatalf("tick result=%+v", result)
	}

	again, err := service.TickSkillSubscriptionCron(context.Background(), assistant.SkillSubscriptionCronTickInput{
		Now: "2026-04-29T08:00:30Z",
	})
	if err != nil {
		t.Fatalf("second TickSkillSubscriptionCron error: %v", err)
	}
	if again.ProcessedCount != 0 {
		t.Fatalf("second tick processed=%d, want 0", again.ProcessedCount)
	}

	messages := notifications.CommandsForUser("user_1")
	if len(messages) != 1 {
		t.Fatalf("notification commands=%d, want 1", len(messages))
	}
	if messages[0].Target.TargetType != "assistant_turn" {
		t.Fatalf("target=%+v", messages[0].Target)
	}
}

func TestTickSkillSubscriptionCronDeliversToConversationDestination(t *testing.T) {
	chat := &fakeChatGroundingClient{}
	notifications := newRecordingNotificationCommandWriter()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithNotificationAppMessageCommandWriter(notifications),
		WithChatGroundingClient(chat),
	)
	service.now = func() time.Time { return time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC) }

	created, err := service.CreateSkillSubscription(context.Background(), "user_1", assistant.CreateSkillSubscriptionInput{
		SkillID:  "news_briefing",
		DomainID: "content",
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			RawText: "每天早上 8 点给群里发科技新闻摘要",
			Queries: []string{"科技新闻"},
		},
		Trigger: assistant.SkillSubscriptionTrigger{Type: "cron", Cron: "0 8 * * *"},
		Destination: assistant.SkillSubscriptionDestination{
			DestinationType: "conversation",
			DestinationID:   "conv_group_1",
		},
	})
	if err != nil {
		t.Fatalf("CreateSkillSubscription error: %v", err)
	}
	if created.Destination.DestinationType != "conversation" || created.Destination.DestinationID != "conv_group_1" {
		t.Fatalf("destination=%+v", created.Destination)
	}

	result, err := service.TickSkillSubscriptionCron(context.Background(), assistant.SkillSubscriptionCronTickInput{
		Now: "2026-04-29T08:00:00Z",
	})
	if err != nil {
		t.Fatalf("TickSkillSubscriptionCron error: %v", err)
	}
	if result.ProcessedCount != 1 || len(result.CreatedTurnIDs) != 1 || len(result.CreatedMessageIDs) != 1 {
		t.Fatalf("tick result=%+v", result)
	}
	if len(chat.sent) != 1 {
		t.Fatalf("chat sent=%d, want 1", len(chat.sent))
	}
	if chat.sent[0].ConversationID != "conv_group_1" || !strings.HasPrefix(chat.sent[0].ClientMsgID, "assistant-proactive-") {
		t.Fatalf("chat message=%+v", chat.sent[0])
	}
	messages := notifications.CommandsForUser("user_1")
	if len(messages) != 0 {
		t.Fatalf("notification commands=%d, want 0 for conversation destination", len(messages))
	}
}

func TestTickSkillSubscriptionCronCreatesM9P0SkillMessages(t *testing.T) {
	notifications := newRecordingNotificationCommandWriter()
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithConversationRunStore(persistence.NewMemoryConversationRunStore()),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithNotificationAppMessageCommandWriter(notifications),
	)
	service.now = func() time.Time { return time.Date(2026, 4, 29, 8, 0, 0, 0, time.UTC) }

	cases := []struct {
		skillID        string
		domainID       string
		rawText        string
		queries        []string
		cron           string
		tickNow        string
		wantTitle      string
		wantSummaryHit []string
	}{
		{
			skillID:        SkillDailyAssistant,
			domainID:       "assistant",
			rawText:        "每天早上提醒我今天的生活、工作和学习计划",
			queries:        []string{"今日待办", "会议安排", "学习计划"},
			cron:           "0 8 * * *",
			tickNow:        "2026-04-29T08:00:00Z",
			wantTitle:      "每日助手：早间计划",
			wantSummaryHit: []string{"为什么提醒你", "会议准备", "学习计划"},
		},
		{
			skillID:        SkillNewsBriefing,
			domainID:       "content",
			rawText:        "每天早上给我人工智能和半导体新闻摘要",
			queries:        []string{"人工智能新闻", "半导体产业"},
			cron:           "0 8 * * *",
			tickNow:        "2026-04-29T08:00:00Z",
			wantTitle:      "新闻简报：人工智能新闻",
			wantSummaryHit: []string{"为什么提醒你", "公开来源", "人工智能新闻"},
		},
		{
			skillID:        SkillStockSentinel,
			domainID:       "finance",
			rawText:        "每天开盘前提醒我关注的股票重大消息",
			queries:        []string{"比亚迪 重大消息", "新能源车 行情"},
			cron:           "0 9 * * *",
			tickNow:        "2026-04-29T09:00:00Z",
			wantTitle:      "股票哨兵：重大消息摘要",
			wantSummaryHit: []string{"为什么提醒你", "消息面", "非投资建议"},
		},
		{
			skillID:        SkillTravelJourneyManager,
			domainID:       "travel",
			rawText:        "每天出发前提醒我行程天气、路况和景点拥堵",
			queries:        []string{"杭州 西湖 天气", "杭州 景区拥堵"},
			cron:           "0 7 * * *",
			tickNow:        "2026-04-29T07:00:00Z",
			wantTitle:      "出行管家：今日行程提醒",
			wantSummaryHit: []string{"为什么提醒你", "天气", "路况"},
		},
	}

	for _, tc := range cases {
		t.Run(tc.skillID, func(t *testing.T) {
			userID := "user_" + tc.skillID
			_, err := service.CreateSkillSubscription(context.Background(), userID, assistant.CreateSkillSubscriptionInput{
				SkillID:  tc.skillID,
				DomainID: tc.domainID,
				SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
					RawText: tc.rawText,
					Queries: tc.queries,
				},
				Trigger: assistant.SkillSubscriptionTrigger{Type: "cron", Cron: tc.cron},
			})
			if err != nil {
				t.Fatalf("CreateSkillSubscription error: %v", err)
			}
			result, err := service.TickSkillSubscriptionCron(context.Background(), assistant.SkillSubscriptionCronTickInput{Now: tc.tickNow})
			if err != nil {
				t.Fatalf("TickSkillSubscriptionCron error: %v", err)
			}
			if result.ProcessedCount != 1 || len(result.CreatedTurnIDs) != 1 || len(result.CreatedMessageIDs) != 1 {
				t.Fatalf("tick result=%+v", result)
			}
			messages := notifications.CommandsForUser(userID)
			if len(messages) != 1 {
				t.Fatalf("notification commands=%d, want 1", len(messages))
			}
			message := messages[0]
			if message.Title != tc.wantTitle {
				t.Fatalf("title=%q, want %q", message.Title, tc.wantTitle)
			}
			for _, hit := range tc.wantSummaryHit {
				if !strings.Contains(message.Summary, hit) {
					t.Fatalf("summary=%q missing %q", message.Summary, hit)
				}
			}
			turn, err := service.GetTurn(context.Background(), userID, message.Target.TargetID)
			if err != nil {
				t.Fatalf("GetTurn error: %v", err)
			}
			if turn.TurnType != "proactive" || turn.SkillID != tc.skillID {
				t.Fatalf("turn=%+v", turn)
			}
		})
	}
}
