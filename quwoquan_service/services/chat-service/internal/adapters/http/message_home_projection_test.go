package http

import (
	"context"
	"testing"

	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

func TestMessageHomeProjection_MentionUnreadCountFromUserState(t *testing.T) {
	t.Parallel()

	handler := ChatHandler{}
	item := application.InboxItem{
		Conversation: model.Conversation{ID: "conv_1", Type: "group", Title: "群"},
		UserState: model.ConversationUserState{
			UserId:             "user_1",
			ConversationId:     "conv_1",
			UnreadCount:        2,
			MentionUnreadCount: 1,
		},
	}
	wire := handler.messageHomeRowToWire(context.Background(), item)
	if wire["mentionUnreadCount"] != 1 {
		t.Fatalf("expected mentionUnreadCount=1, got %v", wire["mentionUnreadCount"])
	}
}

func TestContactHomeCircleRowToWire_UsesCircleContractFields(t *testing.T) {
	t.Parallel()

	wire := contactHomeCircleRowToWire(application.ContactHomeCircleHit{
		CircleID:    "fixture_circle_photo",
		DisplayName: "契约摄影圈",
		AvatarURL:   "media/avatar/s/archived-avatar/circle/fixture_circle_photo/v1/avatar.png",
		Subtitle:    "890",
	})
	if wire["kind"] != "circle" {
		t.Fatalf("expected kind=circle, got %v", wire["kind"])
	}
	if wire["circleId"] != "fixture_circle_photo" {
		t.Fatalf("unexpected circleId: %v", wire["circleId"])
	}
}
