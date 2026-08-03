// Package application is AuthenticationChallenge's inbound authentication
// orchestration adapter. OTP credentials remain transient through this port.
package application

import (
	"context"

	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
)

type Handler struct{ facet challengeapp.CommandFacet }

func NewHandler(facet challengeapp.CommandFacet) *Handler {
	if facet == nil {
		panic("AuthenticationChallenge application adapter requires command facet")
	}
	return &Handler{facet: facet}
}

func (h *Handler) CreateChallenge(
	ctx context.Context,
	command challengeapp.CreateChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return h.facet.CreateChallenge(ctx, command)
}

func (h *Handler) VerifyChallenge(
	ctx context.Context,
	command challengeapp.VerifyChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return h.facet.VerifyChallenge(ctx, command)
}

func (h *Handler) CancelChallenge(
	ctx context.Context,
	command challengeapp.CancelChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return h.facet.CancelChallenge(ctx, command)
}

var _ challengeapp.CommandFacet = (*Handler)(nil)
