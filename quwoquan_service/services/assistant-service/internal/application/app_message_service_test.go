package application

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

func TestAppMessageLifecycle(t *testing.T) {
	service := NewAssistantService(
		persistence.NewMemoryEventStore(),
		persistence.NewMemoryConsentStore(),
		rtredis.NewMemoryClient(),
		WithAppMessageStore(persistence.NewMemoryAppMessageStore()),
	)
	now := time.Date(2026, 4, 29, 2, 0, 0, 0, time.UTC)
	service.now = func() time.Time { return now }

	created, err := service.CreateAppMessage(context.Background(), assistant.CreateAppMessageInput{
		UserID:      "user_1",
		MessageType: "assistant",
		Source:      "assistant_turn",
		SourceID:    "atn_1",
		Title:       "小趣提醒",
		Summary:     "你关注的主题有新进展。",
		Target: assistant.AppMessageTarget{
			TargetType: "assistant_turn",
			TargetID:   "atn_1",
		},
	})
	if err != nil {
		t.Fatalf("CreateAppMessage error: %v", err)
	}
	if created.MessageID == "" {
		t.Fatal("messageId should be generated")
	}
	if created.Destination.Type != "user" || created.Destination.ID != "user_1" {
		t.Fatalf("destination=%+v", created.Destination)
	}

	list, err := service.ListAppMessages(context.Background(), "user_1", 20, "")
	if err != nil {
		t.Fatalf("ListAppMessages error: %v", err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("items=%d, want 1", len(list.Items))
	}
	count, err := service.GetAppMessageUnreadCount(context.Background(), "user_1")
	if err != nil {
		t.Fatalf("GetAppMessageUnreadCount error: %v", err)
	}
	if count.UnreadCount != 1 {
		t.Fatalf("unread=%d, want 1", count.UnreadCount)
	}

	acked, err := service.AckAppMessage(context.Background(), "user_1", created.MessageID)
	if err != nil {
		t.Fatalf("AckAppMessage error: %v", err)
	}
	if acked.AckedAt == nil {
		t.Fatal("ackedAt should be set")
	}
	read, err := service.ReadAppMessage(context.Background(), "user_1", created.MessageID)
	if err != nil {
		t.Fatalf("ReadAppMessage error: %v", err)
	}
	if !read.Read || read.ReadAt == nil {
		t.Fatalf("read state not updated: %+v", read)
	}
}
