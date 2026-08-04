// spec_ref: specs/feature-tree/user-identity-profile-relationship/user-service-cloud-delivery/remote-profile-delivery/spec.md#gwt-001
package local_contract

import (
	"context"
	"crypto/sha256"
	"fmt"
	"testing"
	"time"

	runtimesync "quwoquan_service/runtime/sync"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usersyncstream "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/syncstream"
)

type recordingSyncBackend struct {
	appendUserID    string
	appendPatchType string
	appendPayload   map[string]any
	appendResult    runtimesync.Patch
	pullResult      runtimesync.PullResponse
}

func (backend *recordingSyncBackend) AppendPatch(
	_ context.Context,
	userID string,
	patchType string,
	payload map[string]any,
) (runtimesync.Patch, error) {
	backend.appendUserID = userID
	backend.appendPatchType = patchType
	backend.appendPayload = payload
	return backend.appendResult, nil
}

func (backend *recordingSyncBackend) Pull(
	_ context.Context,
	_ string,
	_ int64,
	_ int,
) (runtimesync.PullResponse, error) {
	return backend.pullResult, nil
}

func TestUserSyncStreamAppendsUserAvatarThroughTypedPort(t *testing.T) {
	occurredAt := time.Date(2026, time.August, 4, 2, 0, 0, 0, time.UTC)
	backend := &recordingSyncBackend{
		appendResult: runtimesync.Patch{
			SyncSeq: 1,
			Type:    "user.avatar.updated",
			Payload: map[string]any{
				"userId":        "user-1",
				"avatarUrl":     "https://cdn.example.com/avatar.png",
				"avatarVersion": int64(3),
			},
			OccurredAt: occurredAt,
		},
	}
	stream := usersyncstream.NewRuntimeUserSyncStream(backend)

	patch, err := stream.AppendUserAvatarPatch(
		context.Background(),
		" account-1 ",
		application.UserAvatarSyncPatchPayload{
			UserID:        " user-1 ",
			AvatarURL:     " https://cdn.example.com/avatar.png ",
			AvatarVersion: 3,
		},
	)
	if err != nil {
		t.Fatalf("append user avatar patch: %v", err)
	}
	if backend.appendUserID != "account-1" ||
		backend.appendPatchType != "user.avatar.updated" ||
		len(backend.appendPayload) != 3 {
		t.Fatalf("runtime envelope was not normalized at infrastructure: %+v", backend)
	}
	if patch.Kind != application.UserSyncPatchKindUserAvatarUpdated ||
		patch.UserAvatarUpdated == nil ||
		patch.ConversationAvatarUpdated != nil ||
		patch.UserAvatarUpdated.UserID != "user-1" ||
		patch.UserAvatarUpdated.AvatarVersion != 3 {
		t.Fatalf("unexpected typed user avatar patch: %+v", patch)
	}
}

func TestUserSyncStreamPullsClosedTypedPatchUnion(t *testing.T) {
	occurredAt := time.Date(2026, time.August, 4, 2, 5, 0, 0, time.UTC)
	groupAvatarSourceHash := fmt.Sprintf(
		"sha256:%x",
		sha256.Sum256([]byte("conversation-1:group-avatar:version-5")),
	)
	backend := &recordingSyncBackend{
		pullResult: runtimesync.PullResponse{
			Patches: []runtimesync.Patch{
				{
					SyncSeq: 1,
					Type:    "user.avatar.updated",
					Payload: map[string]any{
						"userId":        "user-1",
						"avatarUrl":     "https://cdn.example.com/user.png",
						"avatarVersion": float64(8),
					},
					OccurredAt: occurredAt,
				},
				{
					SyncSeq: 2,
					Type:    "conversation.avatar.updated",
					Payload: map[string]any{
						"conversationId":        "conversation-1",
						"avatarUrl":             "https://cdn.example.com/group.png",
						"groupAvatarVersion":    float64(5),
						"groupAvatarSourceHash": groupAvatarSourceHash,
					},
					OccurredAt: occurredAt.Add(time.Second),
				},
			},
			LatestSyncSeq: 2,
		},
	}
	stream := usersyncstream.NewRuntimeUserSyncStream(backend)

	result, err := stream.Pull(context.Background(), "account-1", 0, 200)
	if err != nil {
		t.Fatalf("pull user sync: %v", err)
	}
	if len(result.Patches) != 2 || result.LatestSyncSeq != 2 {
		t.Fatalf("unexpected typed sync slice: %+v", result)
	}
	if result.Patches[0].Kind != application.UserSyncPatchKindUserAvatarUpdated ||
		result.Patches[0].UserAvatarUpdated == nil ||
		result.Patches[0].ConversationAvatarUpdated != nil {
		t.Fatalf("user patch is not a single tagged payload: %+v", result.Patches[0])
	}
	conversationPatch := result.Patches[1]
	if conversationPatch.Kind !=
		application.UserSyncPatchKindConversationAvatarUpdated ||
		conversationPatch.UserAvatarUpdated != nil ||
		conversationPatch.ConversationAvatarUpdated == nil ||
		conversationPatch.ConversationAvatarUpdated.GroupAvatarVersion == nil ||
		*conversationPatch.ConversationAvatarUpdated.GroupAvatarVersion != 5 {
		t.Fatalf("conversation patch is not a single tagged payload: %+v", conversationPatch)
	}
}

func TestUserSyncStreamRejectsUnknownOrMalformedRuntimePatch(t *testing.T) {
	occurredAt := time.Date(2026, time.August, 4, 2, 10, 0, 0, time.UTC)
	cases := []runtimesync.Patch{
		{
			SyncSeq:    1,
			Type:       "persona.profile.updated",
			Payload:    map[string]any{"personaId": "persona-1"},
			OccurredAt: occurredAt,
		},
		{
			SyncSeq: 2,
			Type:    "conversation.avatar.updated",
			Payload: map[string]any{
				"conversationId": "conversation-1",
				"avatarUrl":      "",
			},
			OccurredAt: occurredAt,
		},
	}
	for _, patch := range cases {
		backend := &recordingSyncBackend{
			pullResult: runtimesync.PullResponse{
				Patches:       []runtimesync.Patch{patch},
				LatestSyncSeq: patch.SyncSeq,
			},
		}
		stream := usersyncstream.NewRuntimeUserSyncStream(backend)
		if _, err := stream.Pull(
			context.Background(),
			"account-1",
			0,
			200,
		); err == nil {
			t.Fatalf("patch must fail closed: %+v", patch)
		}
	}
}
