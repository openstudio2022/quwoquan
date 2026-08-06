package application

import (
	"context"
	"errors"
	"strconv"
	"strings"
)

var ErrInvalidDeadLetterRecoveryCommand = errors.New("invalid account-closure dead-letter recovery command")

// DeadLetterRecoveryPort releases the owning consumer's terminal marker while
// preserving the original source stream payload as the only retry input.
type DeadLetterRecoveryPort interface {
	RecoverDeadLetter(context.Context, string) error
}

type RecoverAccountClosureDeadLetterCommand struct {
	SourceStreamID string
	IdempotencyKey string
}

type RecoverAccountClosureDeadLetterResult struct {
	SourceStreamID   string `json:"sourceStreamId"`
	RecoveryAccepted bool   `json:"recoveryAccepted"`
}

// ContentAccountClosureRecoveryCommandFacet owns the recovery use case. HTTP
// decoding and the accountclosure persistence adapter remain outside it.
type ContentAccountClosureRecoveryCommandFacet struct {
	releaser DeadLetterRecoveryPort
}

func NewContentAccountClosureRecoveryCommandFacet(
	releaser DeadLetterRecoveryPort,
) (*ContentAccountClosureRecoveryCommandFacet, error) {
	if releaser == nil {
		return nil, errors.New("account-closure dead-letter releaser is required")
	}
	return &ContentAccountClosureRecoveryCommandFacet{releaser: releaser}, nil
}

func (facet *ContentAccountClosureRecoveryCommandFacet) RecoverAccountClosureDeadLetter(
	ctx context.Context,
	command RecoverAccountClosureDeadLetterCommand,
) (RecoverAccountClosureDeadLetterResult, error) {
	if facet == nil || facet.releaser == nil {
		return RecoverAccountClosureDeadLetterResult{}, errors.New(
			"account-closure recovery command facet is unavailable",
		)
	}
	command.SourceStreamID = strings.TrimSpace(command.SourceStreamID)
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	if command.IdempotencyKey == "" || !isCanonicalRedisStreamID(command.SourceStreamID) {
		return RecoverAccountClosureDeadLetterResult{}, ErrInvalidDeadLetterRecoveryCommand
	}
	if err := facet.releaser.RecoverDeadLetter(ctx, command.SourceStreamID); err != nil {
		return RecoverAccountClosureDeadLetterResult{}, err
	}
	return RecoverAccountClosureDeadLetterResult{
		SourceStreamID:   command.SourceStreamID,
		RecoveryAccepted: true,
	}, nil
}

func isCanonicalRedisStreamID(value string) bool {
	parts := strings.Split(value, "-")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return false
	}
	for _, part := range parts {
		if _, err := strconv.ParseUint(part, 10, 64); err != nil {
			return false
		}
	}
	return true
}
