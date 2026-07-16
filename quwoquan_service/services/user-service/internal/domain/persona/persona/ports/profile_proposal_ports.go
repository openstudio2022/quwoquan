package ports

import (
	"context"

	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
)

type ApplyProfileProposalCommand struct {
	ProposalID             string
	PersonaID              string
	ExpectedPersonaVersion int64
	Changes                personamodel.ProfileChangeSet
}

// ProfileProposalCommandFacade is owned by the target Persona aggregate. A
// caller can mutate Persona only through this boundary and cannot access the
// aggregate Store or any child/value object directly.
type ProfileProposalCommandFacade interface {
	ApplyProfileProposal(context.Context, ApplyProfileProposalCommand) error
}

// ProfileProposalVersionReader is the named cross-aggregate read boundary used
// while confirming a proposal. Callers never load the Persona aggregate or
// infer its version from a UI/cache snapshot.
type ProfileProposalVersionReader interface {
	CurrentVersion(context.Context, string) (int64, error)
}

type ProfileProposalStore interface {
	ApplyProfileProposal(context.Context, ApplyProfileProposalCommand, string) error
}
