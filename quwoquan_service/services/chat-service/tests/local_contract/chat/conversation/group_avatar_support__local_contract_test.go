package local_contract

import (
	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"testing"

	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func TestResolveConversationAvatarURLPrefersPrecomposedGroupAsset(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		ID:                    "conv_test_001",
		Type:                  "group",
		AvatarUrl:             "https://archived.test/user.png",
		GroupAvatarAssetId:    "group_asset_001",
		GroupAvatarVersion:    3,
		GroupAvatarSourceHash: "source_hash_001",
	}

	want := ResolveGroupAvatarURL(conv)
	if want == "" {
		t.Fatal("expected precomposed group avatar url")
	}
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected precomposed avatar url %q, got %q", want, got)
	}
}

func TestResolveConversationAvatarURLUsesArchivedGroupAvatarURL(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		Type:      "group",
		AvatarUrl: "https://archived.test/user.png",
	}

	want := DefaultGroupAvatarURL()
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected default avatar fallback, got %q want %q", got, want)
	}
}

func TestResolveConversationAvatarURLWithMembersUsesCreatorAvatarBeforePrecompose(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		Type:      "group",
		CreatorId: "creator_user",
	}

	members := []model.ConversationMember{
		{UserId: "member_user", AvatarUrl: "https://archived.test/member.png"},
		{UserId: "creator_user", AvatarUrl: "https://archived.test/creator.png"},
	}
	want := "https://archived.test/creator.png"
	if got := ResolveConversationAvatarURLWithMembers(conv, members); got != want {
		t.Fatalf("expected creator avatar fallback %q, got %q", want, got)
	}
}

func TestResolveConversationAvatarURLBuildsPublicURLForDirectObjectKey(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		Type:      "direct",
		AvatarUrl: "media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png",
	}

	want := "https://cdn.test/media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png"
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected direct object-key avatar to resolve to %q, got %q", want, got)
	}
}

func TestResolveConversationAvatarURLFallsBackToDefaultGroupAvatar(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{Type: "group"}
	want := DefaultGroupAvatarURL()
	if want == "" {
		t.Fatal("expected configured default group avatar url")
	}
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected default group avatar url %q, got %q", want, got)
	}
}
