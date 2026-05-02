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

func TestTickSkillSubscriptionCronCreatesProactiveTurnAndAppMessage(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
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

	messages, err := service.ListAppMessages(context.Background(), "user_1", 20, "")
	if err != nil {
		t.Fatalf("ListAppMessages error: %v", err)
	}
	if len(messages.Items) != 1 {
		t.Fatalf("messages=%d, want 1", len(messages.Items))
	}
	if messages.Items[0].Target.TargetType != "assistant_turn" {
		t.Fatalf("target=%+v", messages.Items[0].Target)
	}
}

func TestTickSkillSubscriptionCronCreatesM9P0SkillMessages(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithSkillSubscriptionStore(persistence.NewMemorySkillSubscriptionStore()),
		WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
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
			wantSummaryHit: []string{"为什么提醒你", "今日重点", "学习计划"},
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
			wantSummaryHit: []string{"为什么提醒你", "重大信息", "非投资建议"},
		},
		{
			skillID:        SkillTravelJourneyManager,
			domainID:       "travel",
			rawText:        "每天出发前提醒我行程天气、路况和景点拥堵",
			queries:        []string{"杭州 西湖 天气", "杭州 景区拥堵"},
			cron:           "0 7 * * *",
			tickNow:        "2026-04-29T07:00:00Z",
			wantTitle:      "出行管家：今日行程提醒",
			wantSummaryHit: []string{"为什么提醒你", "天气", "拥堵"},
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
			messages, err := service.ListAppMessages(context.Background(), userID, 20, "")
			if err != nil {
				t.Fatalf("ListAppMessages error: %v", err)
			}
			if len(messages.Items) != 1 {
				t.Fatalf("messages=%d, want 1", len(messages.Items))
			}
			message := messages.Items[0]
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
