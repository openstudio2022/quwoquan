package application

import (
	"context"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
)

type PostReferenceResolver interface {
	ValidateVisiblePost(context.Context, string, string, bool) error
}

type PostAuthority struct {
	resolver PostReferenceResolver
}

func NewPostAuthority(resolver PostReferenceResolver) *PostAuthority {
	return &PostAuthority{resolver: resolver}
}

func (authority *PostAuthority) ValidateVisiblePost(
	ctx context.Context,
	actorPersonaID string,
	postID string,
	visibility model.Visibility,
) error {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	postID = strings.TrimSpace(postID)
	if actorPersonaID == "" || postID == "" || !visibility.Valid() {
		return model.ErrInvalidArgument
	}
	if authority == nil || authority.resolver == nil {
		return ports.ErrPostUnavailable
	}
	return authority.resolver.ValidateVisiblePost(
		ctx, actorPersonaID, postID, visibility == model.VisibilityPublic,
	)
}

var _ ports.PostAuthority = (*PostAuthority)(nil)
