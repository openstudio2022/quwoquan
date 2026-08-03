package event

import (
	"context"
	"strings"

	creatorapp "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
)

type CreatorProfileChanged struct {
	EventType string
	Profile   creatorapp.Profile
	CreatorID string
	Version   int64
}

type Handler struct{ projector *creatorapp.Projector }

func NewHandler(projector *creatorapp.Projector) *Handler {
	if projector == nil {
		panic("CreatorRuntimeProfile event handler requires projector")
	}
	return &Handler{projector: projector}
}

func (h *Handler) Apply(ctx context.Context, event CreatorProfileChanged) (bool, error) {
	switch strings.TrimSpace(event.EventType) {
	case "CreatorReleaseRetired", "PersonaClosed", "UserAccountClosed":
		return h.projector.Delete(ctx, event.CreatorID, event.Version)
	default:
		return h.projector.Project(ctx, event.Profile)
	}
}
