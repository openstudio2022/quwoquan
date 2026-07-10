package application

import (
	"context"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

type fakeIntersectionInboxReader struct {
	reasons   []IntersectionReminderReason
	lastLimit int
}

func (r *fakeIntersectionInboxReader) ListNewIntersectionReasons(_ context.Context, _ string, _ time.Time, limit int) ([]IntersectionReminderReason, error) {
	r.lastLimit = limit
	return r.reasons, nil
}

func TestTickIntersectionRemindersCreatesStructuredAppMessageForFactReason(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
		WithIntersectionInboxReader(&fakeIntersectionInboxReader{reasons: []IntersectionReminderReason{{
			ReasonID:    "reason_1",
			TargetID:    "user_2",
			TargetName:  "阿青",
			Dimension:   "content",
			PrimaryText: "共同讨论",
			IsFact:      true,
		}}}),
	)

	result, err := service.TickIntersectionReminders(context.Background(), IntersectionReminderTickInput{UserID: "user_1"})
	if err != nil {
		t.Fatalf("TickIntersectionReminders error: %v", err)
	}
	if result.ProcessedCount != 1 || len(result.CreatedMessageIDs) != 1 {
		t.Fatalf("result=%+v", result)
	}
	messages, err := service.ListAppMessages(context.Background(), "user_1", 20, "")
	if err != nil {
		t.Fatalf("ListAppMessages error: %v", err)
	}
	if len(messages.Items) != 1 {
		t.Fatalf("messages=%d, want 1", len(messages.Items))
	}
	message := messages.Items[0]
	if message.Target.TargetType != "route" || message.Target.RouteID != "myIntersections" || message.Target.Query["dimension"] != "content" {
		t.Fatalf("structured target=%+v", message.Target)
	}
	if strings.Contains(message.Summary, "收藏") || strings.Contains(message.Summary, "稍后看") || strings.Contains(message.Summary, "关注内容") {
		t.Fatalf("forbidden wording in summary: %q", message.Summary)
	}

	again, err := service.TickIntersectionReminders(context.Background(), IntersectionReminderTickInput{UserID: "user_1"})
	if err != nil {
		t.Fatalf("second TickIntersectionReminders error: %v", err)
	}
	if again.ProcessedCount != 0 {
		t.Fatalf("second result=%+v, want no duplicate", again)
	}
}

func TestTickIntersectionRemindersSkipsAffinityOnlyReason(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
		WithIntersectionInboxReader(&fakeIntersectionInboxReader{reasons: []IntersectionReminderReason{{
			ReasonID:    "reason_affinity",
			TargetID:    "post_1",
			Dimension:   "interest",
			PrimaryText: "可能感兴趣",
			IsFact:      false,
		}}}),
	)

	result, err := service.TickIntersectionReminders(context.Background(), IntersectionReminderTickInput{UserID: "user_1"})
	if err != nil {
		t.Fatalf("TickIntersectionReminders error: %v", err)
	}
	if result.ProcessedCount != 0 || len(result.CreatedMessageIDs) != 0 {
		t.Fatalf("result=%+v, want no messages", result)
	}
}

func TestTickIntersectionRemindersUsesConfiguredPolicyLimit(t *testing.T) {
	reader := &fakeIntersectionInboxReader{}
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
		WithIntersectionInboxReader(reader),
		WithIntersectionReminderPolicy(IntersectionReminderPolicy{
			DefaultLimit: 3,
			MaxLimit:     5,
		}),
	)

	if _, err := service.TickIntersectionReminders(context.Background(), IntersectionReminderTickInput{UserID: "user_1"}); err != nil {
		t.Fatalf("TickIntersectionReminders default limit error: %v", err)
	}
	if reader.lastLimit != 3 {
		t.Fatalf("default limit=%d, want 3", reader.lastLimit)
	}
	if _, err := service.TickIntersectionReminders(context.Background(), IntersectionReminderTickInput{UserID: "user_1", Limit: 99}); err != nil {
		t.Fatalf("TickIntersectionReminders max limit error: %v", err)
	}
	if reader.lastLimit != 5 {
		t.Fatalf("max limit=%d, want 5", reader.lastLimit)
	}
}
