package persona_relationship

import (
	"context"
	"time"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// CommandEvidence is the immutable write coordinate supplied by an App intent.
// IdempotencyKey remains transport-owned; body carries the signed basis and the
// version it was issued against.
type CommandEvidence struct {
	IdempotencyKey  string
	MutationBasis   string
	ExpectedVersion int64
}

type MutationBasisClaims struct {
	ActorPersonaID  string
	TargetPersonaID string
	TargetKind      string
	PairID          string
	ExpectedVersion int64
	AllowedActions  []relmodel.CommandKind
	IssuedAt        time.Time
	AcceptUntil     time.Time
}

type MutationBasisIssuer interface {
	Issue(MutationBasisClaims) (string, error)
	Verify(token string, command relmodel.Command, pairID string) (MutationBasisClaims, error)
	VerifyForRecovery(token string, command relmodel.Command, pairID string) (MutationBasisClaims, error)
	Digest(token string) string
}

type CommandRecoveryResult struct {
	IdempotencyKey   string
	Outcome          relmodel.CommandOutcome
	Replayed         bool
	CommittedVersion *int64
	Changed          *bool
}

type CommandReceiptStore interface {
	Recover(ctx context.Context, actorPersonaID, idempotencyKey string, operation relmodel.CommandKind, targetPersonaID string) (relmodel.MutationResult, bool, error)
	FinalizeExpired(ctx context.Context, actorPersonaID, idempotencyKey string, operation relmodel.CommandKind, targetPersonaID string, acceptUntil time.Time) (relmodel.MutationResult, error)
}
