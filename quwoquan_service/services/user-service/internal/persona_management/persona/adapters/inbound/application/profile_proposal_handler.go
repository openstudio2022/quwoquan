package application

import (
	"context"

	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// ProfileProposalHandler is Persona's typed inbound adapter for approved
// ProfileUpdateProposal mutations. The proposal object cannot reach Persona
// persistence directly.
type ProfileProposalHandler struct {
	facade personaports.ProfileProposalCommandFacade
}

func NewProfileProposalHandler(
	facade personaports.ProfileProposalCommandFacade,
) *ProfileProposalHandler {
	if facade == nil {
		panic("Persona profile proposal adapter requires command facade")
	}
	return &ProfileProposalHandler{facade: facade}
}

func (h *ProfileProposalHandler) ApplyProfileProposal(
	ctx context.Context,
	command personaports.ApplyProfileProposalCommand,
) (personaports.ProfileProposalMutationResult, error) {
	return h.facade.ApplyProfileProposal(ctx, command)
}

func (h *ProfileProposalHandler) RollbackProfileProposal(
	ctx context.Context,
	command personaports.RollbackProfileProposalCommand,
) (personaports.ProfileProposalMutationResult, error) {
	return h.facade.RollbackProfileProposal(ctx, command)
}

var _ personaports.ProfileProposalCommandFacade = (*ProfileProposalHandler)(nil)
