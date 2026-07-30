// spec_ref: specs/feature-tree/runtime/runtime-media/group-avatar-server-precompose-and-unified-sync-contract/spec.md#gwt-001

package local_contract

import (
	"context"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
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
		{
			UserId:        "member_user",
			AvatarUrl:     "media/avatar/s/archived-avatar/user/member_user/v1/avatar.png",
			AvatarVersion: 1,
		},
		{
			UserId:        "creator_user",
			AvatarUrl:     "media/avatar/s/archived-avatar/user/creator_user/v1/avatar.png",
			AvatarVersion: 1,
		},
	}
	want := "https://cdn.test/media/avatar/s/archived-avatar/user/creator_user/v1/avatar.png"
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

func TestResolveConversationAvatarURLRejectsAbsoluteAndUnversionedSources(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")

	for _, raw := range []string{
		"https://untrusted.test/avatar.png",
		"media/avatar/s/archived-avatar/user/user_001/avatar.png",
		"media/avatar/s/archived-avatar/user/user_001/v1/avatar.png?v=1",
	} {
		conv := model.Conversation{Type: "direct", AvatarUrl: raw}
		if got := ResolveConversationAvatarURL(conv); got != "" {
			t.Fatalf("non-canonical avatar source %q must fail closed, got %q", raw, got)
		}
	}
}

func TestGroupAvatarMemberSourcesNeverPassThroughAbsoluteOrMismatchedValues(t *testing.T) {
	ConfigureGroupAvatarCDNBase("https://cdn.test")
	recorder := &recordingGroupAvatarAssetizer{}
	members := []model.ConversationMember{
		{
			UserId:        "absolute_user",
			AvatarUrl:     "https://untrusted.test/avatar.png",
			AvatarVersion: 1,
		},
		{
			UserId:        "canonical_user",
			AvatarUrl:     "media/avatar/s/archived-avatar/user/canonical_user/v1/avatar.png",
			AvatarVersion: 2,
		},
		{
			UserId:        "valid_user",
			AvatarUrl:     "media/avatar/s/archived-avatar/user/valid_user/v1/avatar.png",
			AvatarVersion: 1,
		},
	}

	if _, _, err := RegisterGroupAvatarAsset(
		context.Background(),
		recorder,
		"conversation_001",
		members,
	); err != nil {
		t.Fatalf("register group avatar: %v", err)
	}
	want := []string{
		"",
		"",
		"https://cdn.test/media/avatar/s/archived-avatar/user/valid_user/v1/avatar.png",
	}
	if len(recorder.request.MemberAvatarURLs) != len(want) {
		t.Fatalf("member avatar URL count=%d want=%d", len(recorder.request.MemberAvatarURLs), len(want))
	}
	for index := range want {
		if recorder.request.MemberAvatarURLs[index] != want[index] {
			t.Fatalf(
				"member avatar URL[%d]=%q want=%q",
				index,
				recorder.request.MemberAvatarURLs[index],
				want[index],
			)
		}
	}
}

type recordingGroupAvatarAssetizer struct {
	request runtimemedia.RegisterGroupAvatarRequest
}

func (r *recordingGroupAvatarAssetizer) Register(
	_ context.Context,
	request runtimemedia.RegisterGroupAvatarRequest,
) (runtimemedia.DerivedAvatarAsset, error) {
	r.request = request
	return runtimemedia.DerivedAvatarAsset{}, nil
}
