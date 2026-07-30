package http

import (
	"context"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

func (h *UserHandler) relationshipCapabilityView(
	ctx context.Context,
	viewerID, targetID string,
	rel relmodel.RelationshipState,
	isBlocked, isBlockedBy bool,
) relationshipapp.RelationshipCapabilityView {
	hasPendingGreeting := false
	hasFormalConversation := false
	if h.greeting != nil && viewerID != targetID {
		hasPendingGreeting, _ = h.greeting.HasPendingBetween(ctx, viewerID, targetID)
		hasFormalConversation, _ = h.greeting.HasFormalConversation(ctx, viewerID, targetID)
	}
	return relationshipapp.NewRelationshipCapabilityView(
		relmodel.RelationshipCapabilityFacts{
			ViewerPersonaID:       viewerID,
			TargetPersonaID:       targetID,
			Relationship:          rel,
			IsBlocked:             isBlocked,
			IsBlockedBy:           isBlockedBy,
			HasPendingGreeting:    hasPendingGreeting,
			HasFormalConversation: hasFormalConversation,
		},
	)
}
