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
	ViewerSubAccountID string `json:"viewerSubAccountId"`
	TargetSubAccountID string `json:"targetSubAccountId"`
	RelationState      string `json:"relationState"`
	IsBlocked          bool   `json:"isBlocked"`
	IsBlockedBy        bool   `json:"isBlockedBy"`
}

func newRelationshipViewResponse(
	viewerSubAccountID, targetSubAccountID string,
	state relmodel.RelationshipState,
) relationshipViewResponse {
	return relationshipViewResponse{
		ViewerSubAccountID: viewerSubAccountID,
		TargetSubAccountID: targetSubAccountID,
		RelationState:      state.RelationState(viewerSubAccountID, targetSubAccountID),
		IsBlocked:          state.IsBlocked,
		IsBlockedBy:        state.IsBlockedBy,
	}
}

// blockedListItemResponse is deliberately narrower than Direction. A blocked
// list is an actor-local view and must not expose the internal pair identity or
// the opposite direction's follow state.
type blockedListItemResponse struct {
	TargetSubAccountID string    `json:"targetSubAccountId"`
	DisplayName        string    `json:"displayName"`
	UserHandle         string    `json:"userHandle"`
	AvatarURL          string    `json:"avatarUrl"`
	BlockedAt          time.Time `json:"blockedAt"`
}

func newBlockedListItemResponse(item relports.BlockedListItem) blockedListItemResponse {
	return blockedListItemResponse{
		TargetSubAccountID: item.TargetSubAccountID,
		DisplayName:        item.DisplayName,
		UserHandle:         item.UserHandle,
		AvatarURL:          item.AvatarURL,
		BlockedAt:          item.BlockedAt.UTC(),
	}
}
