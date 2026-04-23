package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	runtimegovernance "quwoquan_service/runtime/governance"
	runtimemedia "quwoquan_service/runtime/media"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const groupAvatarLayoutVersion = "v1"

var configuredGroupAvatarCDNDomain atomic.Value

func ConfigureGroupAvatarCDNDomain(cdnDomain string) {
	configuredGroupAvatarCDNDomain.Store(strings.TrimSpace(cdnDomain))
}

func groupAvatarCDNDomain() string {
	if value, ok := configuredGroupAvatarCDNDomain.Load().(string); ok {
		return value
	}
	return ""
}

func ResolveGroupAvatarURL(conv model.Conversation) string {
	if strings.TrimSpace(conv.GroupAvatarAssetId) == "" || conv.GroupAvatarVersion <= 0 {
		return ""
	}
	ref := runtimemedia.BuildAvatarGroupAssetRef(
		conv.ID,
		conv.GroupAvatarAssetId,
		conv.GroupAvatarVersion,
		conv.GroupAvatarSourceHash,
		groupAvatarCDNDomain(),
	)
	return ref.URL
}

func ResolveConversationAvatarURL(conv model.Conversation) string {
	if url := ResolveGroupAvatarURL(conv); url != "" {
		return url
	}
	return strings.TrimSpace(conv.AvatarUrl)
}

func RecomputeGroupAvatar(
	ctx context.Context,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	conversationID string,
	actorID string,
) error {
	if !runtimegovernance.FeatureEnabled("chat.group_avatar_precompose_enabled", true) {
		return nil
	}
	conv, err := repo.FindConversationByID(ctx, conversationID)
	if err != nil {
		return err
	}
	if conv.Type != "group" && conv.Type != "circle" {
		return nil
	}

	members, err := repo.ListMembers(
		ctx,
		conversationID,
		16,
		"",
		"",
		persistence.SortMembersJoinedAsc,
	)
	if err != nil {
		return err
	}
	top9 := selectTopAvatarMembers(members)
	if len(top9) == 0 {
		return nil
	}

	sourceHash := BuildGroupAvatarSourceHash(top9)
	if sourceHash == strings.TrimSpace(conv.GroupAvatarSourceHash) &&
		conv.GroupAvatarVersion > 0 &&
		strings.TrimSpace(conv.GroupAvatarAssetId) != "" {
		return nil
	}
	if media == nil {
		return nil
	}
	asset, err := media.Register(ctx, runtimemedia.RegisterGroupAvatarRequest{
		ConversationID: conversationID,
		SourceHash:     sourceHash,
		LayoutVersion:  groupAvatarLayoutVersion,
		Contributors:   buildAvatarSources(top9),
	})
	if err != nil {
		return err
	}

	conv.GroupAvatarAssetId = asset.Ref.AssetID
	conv.GroupAvatarVersion = asset.Ref.Version
	conv.GroupAvatarSourceHash = sourceHash
	conv.AvatarUrl = asset.Ref.URL
	conv.UpdatedAt = time.Now()

	if err := repo.UpdateConversation(ctx, conv.ID, conv); err != nil {
		return err
	}
	if !runtimegovernance.FeatureEnabled("runtime.avatar_patch_enabled", true) {
		return nil
	}
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	payload := map[string]any{
		"conversationId":        conv.ID,
		"groupAvatarAssetId":    conv.GroupAvatarAssetId,
		"groupAvatarVersion":    conv.GroupAvatarVersion,
		"groupAvatarSourceHash": conv.GroupAvatarSourceHash,
		"groupAvatarUrl":        asset.Ref.URL,
		"updatedAt":             conv.UpdatedAt,
	}
	if err := publisher.PublishDomainEvent(ctx, event.ConversationAvatarUpdated, conv.ID, actorID, payload); err != nil {
		return err
	}
	if syncPublisher == nil {
		return nil
	}
	memberLimit := conv.MemberCount
	if memberLimit <= 0 {
		memberLimit, _ = repo.CountMembers(ctx, conversationID)
	}
	if memberLimit <= 0 {
		memberLimit = 200
	}
	recipients, err := repo.ListMembers(
		ctx,
		conversationID,
		memberLimit,
		"",
		"",
		persistence.SortMembersJoinedAsc,
	)
	if err != nil {
		return err
	}
	recipientUserIDs := make([]string, 0, len(recipients))
	for _, member := range recipients {
		if strings.TrimSpace(member.UserId) == "" {
			continue
		}
		recipientUserIDs = append(recipientUserIDs, strings.TrimSpace(member.UserId))
	}
	if len(recipientUserIDs) == 0 {
		return nil
	}
	if scheduler != nil {
		return scheduler.EnqueueConversationAvatarPatch(ctx, ConversationAvatarPatchTask{
			ConversationID:   conv.ID,
			ActorID:          actorID,
			Trigger:          "conversation.avatar.updated",
			Payload:          payload,
			RecipientUserIDs: recipientUserIDs,
		})
	}
	for _, member := range recipients {
		if strings.TrimSpace(member.UserId) == "" {
			continue
		}
		if _, err := syncPublisher.AppendPatch(ctx, member.UserId, "conversation.avatar.updated", payload); err != nil {
			return err
		}
	}
	return nil
}

func BuildGroupAvatarSourceHash(members []model.ConversationMember) string {
	hash := sha256.New()
	for _, member := range members {
		hash.Write([]byte(strings.TrimSpace(member.UserId)))
		hash.Write([]byte("|"))
		hash.Write([]byte(strings.TrimSpace(member.AvatarAssetId)))
		hash.Write([]byte("|"))
		hash.Write([]byte(int64String(member.AvatarVersion)))
		hash.Write([]byte("|"))
		hash.Write([]byte(groupAvatarLayoutVersion))
		hash.Write([]byte("|"))
	}
	return hex.EncodeToString(hash.Sum(nil))
}

func selectTopAvatarMembers(members []model.ConversationMember) []model.ConversationMember {
	selected := make([]model.ConversationMember, 0, 9)
	for _, member := range members {
		if strings.TrimSpace(member.MemberType) == "assistant" {
			continue
		}
		selected = append(selected, member)
		if len(selected) >= 9 {
			break
		}
	}
	return selected
}

func buildAvatarSources(members []model.ConversationMember) []runtimemedia.AvatarSource {
	sources := make([]runtimemedia.AvatarSource, 0, len(members))
	for _, member := range members {
		sources = append(sources, runtimemedia.AvatarSource{
			UserID:        strings.TrimSpace(member.UserId),
			AvatarAssetID: strings.TrimSpace(member.AvatarAssetId),
			AvatarVersion: member.AvatarVersion,
		})
	}
	return sources
}

func int64String(value int64) string {
	return strconv.FormatInt(value, 10)
}
