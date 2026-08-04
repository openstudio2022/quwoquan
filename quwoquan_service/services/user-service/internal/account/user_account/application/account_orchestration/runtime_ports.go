package application

import (
	"context"
	"time"
)

type UserEventPublisher interface {
	PublishUserEvent(ctx context.Context, eventType, userID, actorID string, payload map[string]any) error
}

type UserSyncStream interface {
	AppendUserAvatarPatch(
		ctx context.Context,
		accountID string,
		payload UserAvatarSyncPatchPayload,
	) (UserSyncPatch, error)
	Pull(
		ctx context.Context,
		accountID string,
		afterSeq int64,
		limit int,
	) (PullUserSyncSlice, error)
}

type UserSyncPatchKind string

const (
	UserSyncPatchKindUserAvatarUpdated         = UserSyncPatchKind("user_avatar_updated")
	UserSyncPatchKindConversationAvatarUpdated = UserSyncPatchKind("conversation_avatar_updated")
)

type UserAvatarSyncPatchPayload struct {
	UserID        string `json:"userId"`
	AvatarURL     string `json:"avatarUrl"`
	AvatarVersion int64  `json:"avatarVersion"`
}

type ConversationAvatarSyncPatchPayload struct {
	ConversationID        string  `json:"conversationId"`
	AvatarURL             string  `json:"avatarUrl"`
	GroupAvatarVersion    *int64  `json:"groupAvatarVersion,omitempty"`
	GroupAvatarSourceHash *string `json:"groupAvatarSourceHash,omitempty"`
}

type UserSyncPatch struct {
	SyncSeq                   int64                               `json:"syncSeq"`
	Kind                      UserSyncPatchKind                   `json:"kind"`
	UserAvatarUpdated         *UserAvatarSyncPatchPayload         `json:"userAvatarUpdated,omitempty"`
	ConversationAvatarUpdated *ConversationAvatarSyncPatchPayload `json:"conversationAvatarUpdated,omitempty"`
	OccurredAt                time.Time                           `json:"occurredAt"`
}

type PullUserSyncSlice struct {
	Patches        []UserSyncPatch `json:"patches"`
	LatestSyncSeq  int64           `json:"latestSyncSeq"`
	HasMore        bool            `json:"hasMore"`
	RequiresResync bool            `json:"requiresResync"`
}

func requireUserEventPublisher(publisher UserEventPublisher) UserEventPublisher {
	if publisher == nil {
		panic("user application requires UserEventPublisher")
	}
	return publisher
}
