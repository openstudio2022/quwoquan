package http

import (
	"context"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

func (h *UserHandler) buildRelationshipCapabilityView(
	ctx context.Context,
	viewerID, targetID string,
	rel relmodel.RelationshipState,
	isBlocked, isBlockedBy bool,
) map[string]any {
	relationState := "not_following"
	canFollow := true
	canUnfollow := false
	canFollowBack := false
	canGreet := true
	canCreateDirectConversation := false
	canSendMessage := false
	canStartVoiceCall := false
	canStartVideoCall := false
	isMutual := false
	hasPendingGreeting := false
	hasFormalConversation := false

	switch {
	case viewerID == targetID:
		relationState = "self"
		canFollow = false
		canGreet = false
	case rel.IsMutual:
		relationState = "mutual"
		isMutual = true
		canFollow = false
		canUnfollow = true
		canGreet = false
		canCreateDirectConversation = true
		canSendMessage = true
		canStartVoiceCall = true
		canStartVideoCall = true
	case rel.IsFollowing:
		relationState = "following"
		canFollow = false
		canUnfollow = true
	case rel.IsFollowedBy:
		relationState = "followed_by"
		canFollowBack = true
	}

	if h.greeting != nil && viewerID != targetID {
		hasPendingGreeting, _ = h.greeting.HasPendingBetween(ctx, viewerID, targetID)
		hasFormalConversation, _ = h.greeting.HasFormalConversation(ctx, viewerID, targetID)
	}
	if hasFormalConversation {
		canSendMessage = true
	}
	if hasPendingGreeting {
		canGreet = false
	}

	if isBlocked || isBlockedBy {
		canFollow = false
		canFollowBack = false
		canGreet = false
		canCreateDirectConversation = false
		canSendMessage = false
		canStartVoiceCall = false
		canStartVideoCall = false
	}

	return map[string]any{
		"viewerSubAccountId":          viewerID,
		"targetSubAccountId":          targetID,
		"relationState":               relationState,
		"isMutual":                    isMutual,
		"canFollow":                   canFollow,
		"canUnfollow":                 canUnfollow,
		"canFollowBack":               canFollowBack,
		"canGreet":                    canGreet,
		"canOpenConversation":         canCreateDirectConversation || hasFormalConversation,
		"canCreateDirectConversation": canCreateDirectConversation,
		"canSendMessage":              canSendMessage,
		"hasPendingGreeting":          hasPendingGreeting,
		"hasFormalConversation":       hasFormalConversation,
		"canStartVoiceCall":           canStartVoiceCall,
		"canStartVideoCall":           canStartVideoCall,
		"isBlocked":                   isBlocked,
		"isBlockedBy":                 isBlockedBy,
	}
}
