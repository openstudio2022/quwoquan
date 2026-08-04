package syncstream

import (
	"context"
	"fmt"
	"math"
	"strings"

	runtimesync "quwoquan_service/runtime/sync"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

const (
	runtimeUserAvatarPatchType         = "user.avatar.updated"
	runtimeConversationAvatarPatchType = "conversation.avatar.updated"
)

type runtimeSyncBackend interface {
	AppendPatch(
		ctx context.Context,
		userID string,
		patchType string,
		payload map[string]any,
	) (runtimesync.Patch, error)
	Pull(
		ctx context.Context,
		userID string,
		afterSeq int64,
		limit int,
	) (runtimesync.PullResponse, error)
}

// RuntimeUserSyncStream confines the generic Redis patch envelope to the
// UserAccount infrastructure boundary. Application and HTTP layers only see
// the canonical typed patch union.
type RuntimeUserSyncStream struct {
	backend runtimeSyncBackend
}

func NewRuntimeUserSyncStream(backend runtimeSyncBackend) *RuntimeUserSyncStream {
	return &RuntimeUserSyncStream{backend: backend}
}

func (stream *RuntimeUserSyncStream) AppendUserAvatarPatch(
	ctx context.Context,
	accountID string,
	payload application.UserAvatarSyncPatchPayload,
) (application.UserSyncPatch, error) {
	if stream == nil || stream.backend == nil {
		return application.UserSyncPatch{}, fmt.Errorf(
			"user sync runtime backend is required",
		)
	}
	if strings.TrimSpace(accountID) == "" ||
		strings.TrimSpace(payload.UserID) == "" ||
		strings.TrimSpace(payload.AvatarURL) == "" ||
		payload.AvatarVersion < 0 {
		return application.UserSyncPatch{}, fmt.Errorf(
			"valid account, user avatar identity, URL and version are required",
		)
	}
	patch, err := stream.backend.AppendPatch(
		ctx,
		strings.TrimSpace(accountID),
		runtimeUserAvatarPatchType,
		map[string]any{
			"userId":        strings.TrimSpace(payload.UserID),
			"avatarUrl":     strings.TrimSpace(payload.AvatarURL),
			"avatarVersion": payload.AvatarVersion,
		},
	)
	if err != nil {
		return application.UserSyncPatch{}, err
	}
	return mapRuntimePatch(patch)
}

func (stream *RuntimeUserSyncStream) Pull(
	ctx context.Context,
	accountID string,
	afterSeq int64,
	limit int,
) (application.PullUserSyncSlice, error) {
	if stream == nil || stream.backend == nil {
		return application.PullUserSyncSlice{}, fmt.Errorf(
			"user sync runtime backend is required",
		)
	}
	response, err := stream.backend.Pull(
		ctx,
		strings.TrimSpace(accountID),
		afterSeq,
		limit,
	)
	if err != nil {
		return application.PullUserSyncSlice{}, err
	}
	patches := make([]application.UserSyncPatch, 0, len(response.Patches))
	for _, patch := range response.Patches {
		mapped, mapErr := mapRuntimePatch(patch)
		if mapErr != nil {
			return application.PullUserSyncSlice{}, mapErr
		}
		patches = append(patches, mapped)
	}
	return application.PullUserSyncSlice{
		Patches:        patches,
		LatestSyncSeq:  response.LatestSyncSeq,
		HasMore:        response.HasMore,
		RequiresResync: response.RequiresResync,
	}, nil
}

func mapRuntimePatch(
	patch runtimesync.Patch,
) (application.UserSyncPatch, error) {
	if patch.SyncSeq <= 0 || patch.OccurredAt.IsZero() {
		return application.UserSyncPatch{}, fmt.Errorf(
			"sync patch requires positive sequence and occurredAt",
		)
	}
	mapped := application.UserSyncPatch{
		SyncSeq:    patch.SyncSeq,
		OccurredAt: patch.OccurredAt.UTC(),
	}
	switch strings.TrimSpace(patch.Type) {
	case runtimeUserAvatarPatchType:
		userID, err := requiredString(patch.Payload, "userId")
		if err != nil {
			return application.UserSyncPatch{}, err
		}
		avatarURL, err := requiredString(patch.Payload, "avatarUrl")
		if err != nil {
			return application.UserSyncPatch{}, err
		}
		avatarVersion, err := requiredInt64(patch.Payload, "avatarVersion")
		if err != nil || avatarVersion < 0 {
			return application.UserSyncPatch{}, fmt.Errorf(
				"user avatar sync patch requires a non-negative avatarVersion",
			)
		}
		mapped.Kind = application.UserSyncPatchKindUserAvatarUpdated
		mapped.UserAvatarUpdated = &application.UserAvatarSyncPatchPayload{
			UserID:        userID,
			AvatarURL:     avatarURL,
			AvatarVersion: avatarVersion,
		}
	case runtimeConversationAvatarPatchType:
		conversationID, err := requiredString(patch.Payload, "conversationId")
		if err != nil {
			return application.UserSyncPatch{}, err
		}
		avatarURL, err := requiredString(patch.Payload, "avatarUrl")
		if err != nil {
			return application.UserSyncPatch{}, err
		}
		groupAvatarVersion, err := optionalInt64(
			patch.Payload,
			"groupAvatarVersion",
		)
		if err != nil ||
			(groupAvatarVersion != nil && *groupAvatarVersion < 0) {
			return application.UserSyncPatch{}, fmt.Errorf(
				"conversation avatar sync patch has an invalid groupAvatarVersion",
			)
		}
		groupAvatarSourceHash := optionalString(
			patch.Payload,
			"groupAvatarSourceHash",
		)
		mapped.Kind = application.UserSyncPatchKindConversationAvatarUpdated
		mapped.ConversationAvatarUpdated =
			&application.ConversationAvatarSyncPatchPayload{
				ConversationID:        conversationID,
				AvatarURL:             avatarURL,
				GroupAvatarVersion:    groupAvatarVersion,
				GroupAvatarSourceHash: groupAvatarSourceHash,
			}
	default:
		return application.UserSyncPatch{}, fmt.Errorf(
			"unsupported user sync patch kind",
		)
	}
	return mapped, nil
}

func requiredString(payload map[string]any, field string) (string, error) {
	value, ok := payload[field].(string)
	value = strings.TrimSpace(value)
	if !ok || value == "" {
		return "", fmt.Errorf("sync patch requires %s", field)
	}
	return value, nil
}

func optionalString(payload map[string]any, field string) *string {
	value, ok := payload[field].(string)
	value = strings.TrimSpace(value)
	if !ok || value == "" {
		return nil
	}
	return &value
}

func requiredInt64(payload map[string]any, field string) (int64, error) {
	value, ok, err := int64Value(payload[field])
	if err != nil || !ok {
		return 0, fmt.Errorf("sync patch requires integer %s", field)
	}
	return value, nil
}

func optionalInt64(payload map[string]any, field string) (*int64, error) {
	raw, exists := payload[field]
	if !exists || raw == nil {
		return nil, nil
	}
	value, ok, err := int64Value(raw)
	if err != nil || !ok {
		return nil, fmt.Errorf("sync patch field %s must be an integer", field)
	}
	return &value, nil
}

func int64Value(raw any) (int64, bool, error) {
	switch value := raw.(type) {
	case int:
		return int64(value), true, nil
	case int32:
		return int64(value), true, nil
	case int64:
		return value, true, nil
	case float64:
		if math.Trunc(value) != value ||
			value < math.MinInt64 ||
			value > math.MaxInt64 {
			return 0, false, fmt.Errorf("number is not an int64")
		}
		return int64(value), true, nil
	default:
		return 0, false, nil
	}
}
