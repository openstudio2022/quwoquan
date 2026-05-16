package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
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

var configuredGroupAvatarCDNBase atomic.Value
var configuredDefaultGroupAvatarURL atomic.Value

// ConfigureGroupAvatarCDNBase 设置群头像对外 URL 的 CDN base（须含 scheme）。
func ConfigureGroupAvatarCDNBase(baseURL string) {
	normalized := runtimemedia.NormalizeMediaCDNBase(strings.TrimSpace(baseURL))
	configuredGroupAvatarCDNBase.Store(normalized)
	configuredDefaultGroupAvatarURL.Store(runtimemedia.BuildDefaultGroupAvatarURL(normalized))
}

func groupAvatarCDNBase() string {
	if value, ok := configuredGroupAvatarCDNBase.Load().(string); ok {
		return value
	}
	return ""
}

func DefaultGroupAvatarURL() string {
	if value, ok := configuredDefaultGroupAvatarURL.Load().(string); ok {
		return strings.TrimSpace(value)
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
		groupAvatarCDNBase(),
	)
	return ref.URL
}

func ResolveConversationAvatarURL(conv model.Conversation) string {
	t := PublicConversationType(conv.Type, conv.CircleId)
	if t == conversationTypeDirect {
		return resolveConversationAvatarURLValue(conv.AvatarUrl, 0)
	}
	if t == conversationTypeGroup {
		if u := ResolveGroupAvatarURL(conv); u != "" {
			return u
		}
		if u := resolveConversationAvatarURLValue(conv.AvatarUrl, conv.GroupAvatarVersion); u != "" {
			return u
		}
		return DefaultGroupAvatarURL()
	}
	return resolveConversationAvatarURLValue(conv.AvatarUrl, 0)
}

func RegisterGroupAvatarAsset(
	ctx context.Context,
	media GroupAvatarAssetizer,
	conversationID string,
	members []model.ConversationMember,
) (runtimemedia.DerivedAvatarAsset, string, error) {
	if media == nil {
		return runtimemedia.DerivedAvatarAsset{}, "", fmt.Errorf("group avatar assetizer is required")
	}
	top9 := selectTopAvatarMembers(members)
	if len(top9) == 0 {
		return runtimemedia.DerivedAvatarAsset{}, "", fmt.Errorf("group avatar render requires at least one member")
	}
	sourceHash := BuildGroupAvatarSourceHash(top9)
	memberAvatarURLs := make([]string, 0, len(top9))
	for _, member := range top9 {
		memberAvatarURLs = append(memberAvatarURLs, resolveGroupAvatarSourceURL(member.AvatarUrl))
	}
	asset, err := media.Register(ctx, runtimemedia.RegisterGroupAvatarRequest{
		ConversationID:   conversationID,
		SourceHash:       sourceHash,
		LayoutVersion:    groupAvatarLayoutVersion,
		Contributors:     buildAvatarSources(top9),
		MemberAvatarURLs: memberAvatarURLs,
	})
	if err != nil {
		return runtimemedia.DerivedAvatarAsset{}, "", err
	}
	return asset, sourceHash, nil
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
	if !IsGroupConversation(*conv) {
		return nil
	}
	if strings.TrimSpace(conv.Status) != "active" {
		return nil
	}

	memberLimit := conv.MemberCount
	if memberLimit < 16 {
		memberLimit = 16
	}
	if memberLimit > 200 {
		memberLimit = 200
	}
	members, err := repo.ListMembers(
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
	top9 := selectTopAvatarMembers(members)
	if len(top9) == 0 {
		return nil
	}

	sourceHash := BuildGroupAvatarSourceHash(top9)
	if sourceHash == strings.TrimSpace(conv.GroupAvatarSourceHash) &&
		conv.GroupAvatarVersion > 0 &&
		strings.TrimSpace(conv.GroupAvatarAssetId) != "" {
		return ensureConversationAvatarNotification(ctx, repo, publisher, syncPublisher, scheduler, conv, actorID)
	}
	if media == nil {
		return nil
	}
	asset, sourceHash, err := RegisterGroupAvatarAsset(ctx, media, conversationID, top9)
	if err != nil {
		return err
	}

	conv.GroupAvatarAssetId = asset.Ref.AssetID
	conv.GroupAvatarVersion = asset.Ref.Version
	conv.GroupAvatarSourceHash = sourceHash
	conv.AvatarUrl = asset.Ref.URL
	conv.UpdatedAt = time.Now()

	avatarPatchEnabled := runtimegovernance.FeatureEnabled("runtime.avatar_patch_enabled", true)
	payload := map[string]any{
		"conversationId":        conv.ID,
		"avatarUrl":             asset.Ref.URL,
		"groupAvatarAssetId":    conv.GroupAvatarAssetId,
		"groupAvatarVersion":    conv.GroupAvatarVersion,
		"groupAvatarSourceHash": conv.GroupAvatarSourceHash,
		"updatedAt":             conv.UpdatedAt,
	}
	recipients, recipientUserIDs, err := resolveConversationAvatarRecipients(ctx, repo, conv)
	if err != nil {
		return err
	}

	if err := repo.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := repo.UpdateConversation(txCtx, conv.ID, conv); err != nil {
			return err
		}
		if !avatarPatchEnabled || scheduler == nil || len(recipientUserIDs) == 0 {
			return nil
		}
		return scheduler.EnqueueConversationAvatarPatch(txCtx, ConversationAvatarPatchTask{
			ConversationID:   conv.ID,
			ActorID:          actorID,
			Trigger:          "conversation.avatar.updated",
			Payload:          payload,
			RecipientUserIDs: recipientUserIDs,
		})
	}); err != nil {
		slog.Error(
			"group avatar asset registered but conversation transaction failed",
			"err", err,
			"conversationId", conv.ID,
			"assetId", asset.Ref.AssetID,
			"sourceHash", sourceHash,
		)
		return err
	}

	if !avatarPatchEnabled {
		return nil
	}
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	if err := publisher.PublishDomainEvent(ctx, event.ConversationAvatarUpdated, conv.ID, actorID, payload); err != nil {
		return err
	}
	if syncPublisher == nil {
		return nil
	}
	if scheduler != nil {
		return nil
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

func ensureConversationAvatarNotification(
	ctx context.Context,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	syncPublisher UserSyncPublisher,
	scheduler GroupAvatarTaskScheduler,
	conv *model.Conversation,
	actorID string,
) error {
	if !runtimegovernance.FeatureEnabled("runtime.avatar_patch_enabled", true) {
		return nil
	}
	payload := map[string]any{
		"conversationId":        conv.ID,
		"avatarUrl":             ResolveConversationAvatarURL(*conv),
		"groupAvatarAssetId":    conv.GroupAvatarAssetId,
		"groupAvatarVersion":    conv.GroupAvatarVersion,
		"groupAvatarSourceHash": conv.GroupAvatarSourceHash,
		"updatedAt":             conv.UpdatedAt,
	}
	recipients, recipientUserIDs, err := resolveConversationAvatarRecipients(ctx, repo, conv)
	if err != nil {
		return err
	}
	if scheduler != nil && len(recipientUserIDs) > 0 {
		if err := repo.RunInTransaction(ctx, func(txCtx context.Context) error {
			return scheduler.EnqueueConversationAvatarPatch(txCtx, ConversationAvatarPatchTask{
				ConversationID:   conv.ID,
				ActorID:          actorID,
				Trigger:          "conversation.avatar.updated",
				Payload:          payload,
				RecipientUserIDs: recipientUserIDs,
			})
		}); err != nil {
			return err
		}
	}
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	if err := publisher.PublishDomainEvent(ctx, event.ConversationAvatarUpdated, conv.ID, actorID, payload); err != nil {
		return err
	}
	if syncPublisher == nil || scheduler != nil {
		return nil
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

func resolveConversationAvatarRecipients(
	ctx context.Context,
	repo persistence.ChatRepository,
	conv *model.Conversation,
) ([]model.ConversationMember, []string, error) {
	memberLimit := conv.MemberCount
	if memberLimit <= 0 {
		memberLimit, _ = repo.CountMembers(ctx, conv.ID)
	}
	if memberLimit <= 0 {
		memberLimit = 200
	}
	recipients, err := repo.ListMembers(
		ctx,
		conv.ID,
		memberLimit,
		"",
		"",
		persistence.SortMembersJoinedAsc,
	)
	if err != nil {
		return nil, nil, err
	}
	recipientUserIDs := make([]string, 0, len(recipients))
	for _, member := range recipients {
		if strings.TrimSpace(member.MemberType) != "user" {
			continue
		}
		if strings.TrimSpace(member.UserId) == "" {
			continue
		}
		recipientUserIDs = append(recipientUserIDs, strings.TrimSpace(member.UserId))
	}
	if len(recipientUserIDs) == 0 {
		return recipients, nil, nil
	}
	return recipients, recipientUserIDs, nil
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
		hash.Write([]byte(strings.TrimSpace(member.AvatarUrl)))
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

func resolveGroupAvatarSourceURL(raw string) string {
	source := strings.TrimSpace(raw)
	if source == "" {
		return ""
	}
	if strings.Contains(source, "://") {
		return source
	}
	return runtimemedia.BuildPublicMediaURL(groupAvatarCDNBase(), source, 0)
}

func resolveConversationAvatarURLValue(raw string, version int64) string {
	source := strings.TrimSpace(raw)
	if source == "" {
		return ""
	}
	if strings.Contains(source, "://") {
		return source
	}
	if publicURL := runtimemedia.BuildPublicMediaURL(groupAvatarCDNBase(), source, version); publicURL != "" {
		return publicURL
	}
	return source
}

func int64String(value int64) string {
	return strconv.FormatInt(value, 10)
}
