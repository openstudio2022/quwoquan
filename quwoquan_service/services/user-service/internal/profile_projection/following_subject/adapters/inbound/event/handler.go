// Package event is FollowingSubject's typed subscription adapter.
package event

import (
	"context"

	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
)

type Handler struct {
	projector *followingapp.FollowingSubjectProjector
}

func NewHandler(projector *followingapp.FollowingSubjectProjector) *Handler {
	if projector == nil {
		panic("FollowingSubject event handler requires projector")
	}
	return &Handler{projector: projector}
}

func (h *Handler) Apply(ctx context.Context, event followingapp.FollowChangedEvent) error {
	return h.projector.Apply(ctx, event)
}
