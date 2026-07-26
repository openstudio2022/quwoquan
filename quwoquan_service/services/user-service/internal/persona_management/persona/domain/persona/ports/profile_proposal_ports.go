package ports

import (
	"context"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
)

type ApplyProfileProposalCommand struct {
	ProposalID             string
	PersonaID              string
	ExpectedPersonaVersion int64
	Changes                personamodel.ProfileChangeSet
}

type RollbackProfileProposalCommand struct {
	ProposalID             string
	PersonaID              string
	ExpectedPersonaVersion int64
	Snapshot               personamodel.ProfileSnapshot
}

type ProfileProposalMutationResult struct {
	Before     personamodel.ProfileSnapshot
	After      personamodel.ProfileSnapshot
	OccurredAt time.Time
}

// ProfileProposalCommandFacade is owned by the target Persona aggregate. A
// caller can mutate Persona only through this boundary and cannot access the
// aggregate Store or any child/value object directly.
type ProfileProposalCommandFacade interface {
	ApplyProfileProposal(context.Context, ApplyProfileProposalCommand) (ProfileProposalMutationResult, error)
	RollbackProfileProposal(context.Context, RollbackProfileProposalCommand) (ProfileProposalMutationResult, error)
}

// ProfileProposalVersionReader is the named cross-aggregate read boundary used
// while confirming a proposal. Callers never load the Persona aggregate or
// infer its version from a UI/cache snapshot.
type ProfileProposalVersionReader interface {
	CurrentVersion(context.Context, string) (int64, error)
}

type ProfileProposalStore interface {
	ApplyProfileProposal(
		context.Context,
		ApplyProfileProposalCommand,
		string,
	) (ProfileProposalMutationResult, error)
	RollbackProfileProposal(
		context.Context,
		RollbackProfileProposalCommand,
		string,
	) (ProfileProposalMutationResult, error)
}
