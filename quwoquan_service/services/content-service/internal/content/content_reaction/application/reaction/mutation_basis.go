package reaction

import (
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	"time"
)

type MutationEvidence struct {
	MutationBasis   string
	ExpectedVersion int64
}
type MutationBasisClaims struct {
	Identity        reactiondomain.Identity
	ExpectedVersion int64
	AllowedValues   []reactiondomain.Value
	IssuedAt        time.Time
	AcceptUntil     time.Time
}
type MutationBasisIssuer interface {
	Issue(MutationBasisClaims) (string, error)
	Verify(string, reactiondomain.Identity, reactiondomain.Value, int64) (MutationBasisClaims, error)
	VerifyForRecovery(string, reactiondomain.Identity, reactiondomain.Value, int64) (MutationBasisClaims, error)
	Digest(string) string
}
