// Package application adapts UserAccount authentication orchestration to the
// AccountSession object's only command facet.
package application

import (
	"context"

	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
)

type Handler struct{ facet sessionapp.CommandFacet }

func NewHandler(facet sessionapp.CommandFacet) *Handler {
	if facet == nil {
		panic("AccountSession application adapter requires command facet")
	}
	return &Handler{facet: facet}
}

func (h *Handler) Issue(ctx context.Context, command sessionapp.IssueCommand) (sessionapp.SessionResult, error) {
	return h.facet.Issue(ctx, command)
}

func (h *Handler) Rotate(ctx context.Context, command sessionapp.RotateCommand) (sessionapp.SessionResult, error) {
	return h.facet.Rotate(ctx, command)
}

func (h *Handler) Logout(ctx context.Context, command sessionapp.LogoutCommand) error {
	return h.facet.Logout(ctx, command)
}

func (h *Handler) Revoke(ctx context.Context, command sessionapp.RevokeCommand) error {
	return h.facet.Revoke(ctx, command)
}

var _ sessionapp.CommandFacet = (*Handler)(nil)
