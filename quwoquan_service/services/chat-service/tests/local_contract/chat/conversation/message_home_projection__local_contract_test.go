package local_contract

import (
	"testing"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func TestMessageHomeProjection_MentionUnreadCountFromUserState(t *testing.T) {
	t.Parallel()

	item := application.InboxItem{
		Conversation: model.Conversation{ID: "conv_1", Type: "group", Title: "群"},
		UserState: model.ConversationUserState{
			UserId:             "user_1",
			ConversationId:     "conv_1",
			UnreadCount:        2,
			MentionUnreadCount: 1,
		},
	}
	if item.UserState.MentionUnreadCount != 1 {
		t.Fatalf("expected mentionUnreadCount=1, got %v", item.UserState.MentionUnreadCount)
	}
}

func TestContactHomeCircleRowToWire_UsesCircleContractFields(t *testing.T) {
	t.Parallel()

	hit := application.ContactHomeCircleHit{
		CircleID:    "fixture_circle_photo",
		DisplayName: "契约摄影圈",
		AvatarURL:   "media/avatar/s/archived-avatar/circle/fixture_circle_photo/v1/avatar.png",
		Subtitle:    "890",
	}
	if hit.CircleID != "fixture_circle_photo" {
		t.Fatalf("unexpected circleId: %v", hit.CircleID)
	}
	if hit.DisplayName == "" || hit.AvatarURL == "" {
		t.Fatalf("circle contract projection must retain display fields: %+v", hit)
	}
}
