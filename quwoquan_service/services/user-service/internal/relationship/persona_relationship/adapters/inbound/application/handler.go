package application

import (
	"context"

	relapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

type Handler struct{ facade relapp.Facade }

func NewHandler(facade relapp.Facade) *Handler {
	if facade == nil {
		panic("PersonaRelationship application adapter requires facade")
	}
	return &Handler{facade: facade}
}

func (h *Handler) Follow(ctx context.Context, source, target, origin, key string) (relmodel.MutationResult, error) {
	return h.facade.Follow(ctx, source, target, origin, key)
}
func (h *Handler) Unfollow(ctx context.Context, source, target, key string) (relmodel.MutationResult, error) {
	return h.facade.Unfollow(ctx, source, target, key)
}
func (h *Handler) Block(ctx context.Context, source, target, key string) (relmodel.MutationResult, error) {
	return h.facade.Block(ctx, source, target, key)
}
func (h *Handler) Unblock(ctx context.Context, source, target, key string) (relmodel.MutationResult, error) {
	return h.facade.Unblock(ctx, source, target, key)
}
func (h *Handler) GetRelationship(ctx context.Context, source, target string) (relmodel.RelationshipState, error) {
	return h.facade.GetRelationship(ctx, source, target)
}
func (h *Handler) CheckBlocked(ctx context.Context, source, target string) (bool, error) {
	return h.facade.CheckBlocked(ctx, source, target)
}
func (h *Handler) ListFollowing(ctx context.Context, source, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return h.facade.ListFollowing(ctx, source, cursor, limit)
}
func (h *Handler) ListFollowers(ctx context.Context, target, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return h.facade.ListFollowers(ctx, target, cursor, limit)
}
func (h *Handler) ListBlocked(ctx context.Context, source, cursor string, limit int) ([]relports.BlockedListItem, string, error) {
	return h.facade.ListBlocked(ctx, source, cursor, limit)
}

var _ relapp.Facade = (*Handler)(nil)
