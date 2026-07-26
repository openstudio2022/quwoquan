package persona

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// ProfileProposalFacade is the target aggregate command boundary used by
// ProfileUpdateProposal. It owns validation and delegates one typed atomic
// commit to the Persona-specific Store.
type ProfileProposalFacade struct {
	store personaports.ProfileProposalStore
}

func NewProfileProposalFacade(store personaports.ProfileProposalStore) (*ProfileProposalFacade, error) {
	if store == nil {
		return nil, errors.New("Persona profile proposal Store is required")
	}
	return &ProfileProposalFacade{store: store}, nil
}

func (f *ProfileProposalFacade) ApplyProfileProposal(
	ctx context.Context,
	command personaports.ApplyProfileProposalCommand,
) error {
	command.ProposalID = strings.TrimSpace(command.ProposalID)
	command.PersonaID = strings.TrimSpace(command.PersonaID)
	if command.ProposalID == "" || len(command.ProposalID) > 64 ||
		command.PersonaID == "" || len(command.PersonaID) > 96 {
		return errors.New("proposalId and personaId are required within persistence limits")
	}
	if command.ExpectedPersonaVersion <= 0 {
		return personamodel.ErrVersionConflict
	}
	if err := command.Changes.Validate(); err != nil {
		return err
	}
	payload, err := json.Marshal(command)
	if err != nil {
		return err
	}
	digest := sha256.Sum256(payload)
	return f.store.ApplyProfileProposal(ctx, command, fmt.Sprintf("%x", digest[:]))
}

var _ personaports.ProfileProposalCommandFacade = (*ProfileProposalFacade)(nil)
