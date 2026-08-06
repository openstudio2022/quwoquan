package application

import (
	"context"
	"errors"
)

// AccountClosureDeadLetterReleaser is the object-owned port for releasing a
// terminal UserAccountClosed delivery marker. The original event remains in
// its source PEL; recovery never reconstructs payload from the sanitized DLQ.
type AccountClosureDeadLetterReleaser interface {
	RecoverDeadLetter(context.Context, string) error
}

// SearchRequestAccountClosureRecoveryCommandFacet is the production command
// boundary used by the operator-only HTTP recovery operation.
type SearchRequestAccountClosureRecoveryCommandFacet struct {
	releaser AccountClosureDeadLetterReleaser
}

func NewSearchRequestAccountClosureRecoveryCommandFacet(
	releaser AccountClosureDeadLetterReleaser,
) (*SearchRequestAccountClosureRecoveryCommandFacet, error) {
	if releaser == nil {
		return nil, errors.New(
			"search request account-closure recovery requires a releaser",
		)
	}
	return &SearchRequestAccountClosureRecoveryCommandFacet{
		releaser: releaser,
	}, nil
}

func (facet *SearchRequestAccountClosureRecoveryCommandFacet) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if facet == nil || facet.releaser == nil {
		return errors.New(
			"search request account-closure recovery is not configured",
		)
	}
	return facet.releaser.RecoverDeadLetter(ctx, sourceStreamID)
}
