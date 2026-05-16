package application

import (
	"testing"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

func TestResolveConversationAvatarURLPrefersPrecomposedGroupAsset(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		ID:                    "conv_test_001",
		Type:                  conversationTypeGroup,
		AvatarUrl:             "https://legacy.test/user.png",
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

func TestResolveConversationAvatarURLFallsBackToLegacyAvatarURL(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		Type:      conversationTypeGroup,
		AvatarUrl: "https://legacy.test/user.png",
	}

	if got := ResolveConversationAvatarURL(conv); got != "https://legacy.test/user.png" {
		t.Fatalf("expected legacy avatar url fallback, got %q", got)
	}
}

func TestResolveConversationAvatarURLBuildsPublicURLFromObjectKeyFallback(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		Type:               conversationTypeGroup,
		AvatarUrl:          "media/avatar/group/fixture_conv_group/v1/composite.png",
		GroupAvatarVersion: 1,
	}

	want := "https://cdn.test/media/avatar/group/fixture_conv_group/v1/composite.png?v=1"
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected object-key fallback to public url %q, got %q", want, got)
	}
}

func TestResolveConversationAvatarURLBuildsPublicURLForDirectObjectKey(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{
		Type:      conversationTypeDirect,
		AvatarUrl: "media/avatar/user/fixture_user_friend/v1/avatar.png",
	}

	want := "https://cdn.test/media/avatar/user/fixture_user_friend/v1/avatar.png"
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected direct object-key avatar to resolve to %q, got %q", want, got)
	}
}

func TestResolveConversationAvatarURLFallsBackToDefaultGroupAvatar(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	conv := model.Conversation{Type: conversationTypeGroup}
	want := DefaultGroupAvatarURL()
	if want == "" {
		t.Fatal("expected configured default group avatar url")
	}
	if got := ResolveConversationAvatarURL(conv); got != want {
		t.Fatalf("expected default group avatar url %q, got %q", want, got)
	}
}

func TestResolveGroupAvatarSourceURLBuildsPublicURLFromObjectKey(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	got := resolveGroupAvatarSourceURL("media/avatar/user/u1/v1/avatar.png")
	want := "https://cdn.test/media/avatar/user/u1/v1/avatar.png"
	if got != want {
		t.Fatalf("expected normalized source url %q, got %q", want, got)
	}
}
