package http

import (
	"time"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

// relationshipViewResponse is the REST projection of a relationship aggregate.
// It prevents pair identifiers, versions, and bidirectional storage state from
// leaking through the query endpoint.
type relationshipViewResponse struct {
	ViewerPersonaID string `json:"viewerPersonaId"`
	TargetPersonaID string `json:"targetPersonaId"`
	RelationState   string `json:"relationState"`
	IsBlocked       bool   `json:"isBlocked"`
	IsBlockedBy     bool   `json:"isBlockedBy"`
}

func newRelationshipViewResponse(
	viewerPersonaID, targetPersonaID string,
	state relmodel.RelationshipState,
) relationshipViewResponse {
	return relationshipViewResponse{
		ViewerPersonaID: viewerPersonaID,
		TargetPersonaID: targetPersonaID,
		RelationState:   state.RelationState(viewerPersonaID, targetPersonaID),
		IsBlocked:       state.IsBlocked,
		IsBlockedBy:     state.IsBlockedBy,
	}
}

// blockedListItemResponse is deliberately narrower than Direction. A blocked
// list is an actor-local view and must not expose the internal pair identity or
// the opposite direction's follow state.
type blockedListItemResponse struct {
	TargetPersonaID string    `json:"targetPersonaId"`
	DisplayName     string    `json:"displayName"`
	UserHandle      string    `json:"userHandle"`
	AvatarURL       string    `json:"avatarUrl"`
	BlockedAt       time.Time `json:"blockedAt"`
}

func newBlockedListItemResponse(item relports.BlockedListItem) blockedListItemResponse {
	return blockedListItemResponse{
		TargetPersonaID: item.TargetPersonaID,
		DisplayName:     item.DisplayName,
		UserHandle:      item.UserHandle,
		AvatarURL:       item.AvatarURL,
		BlockedAt:       item.BlockedAt.UTC(),
	}
}
