package reaction_test

import (
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	"time"
)

type testBasis struct{}

func (testBasis) Issue(c reactionapp.MutationBasisClaims) (string, error) { return "test-basis", nil }
func (testBasis) Verify(_ string, i reactiondomain.Identity, v reactiondomain.Value, ver int64) (reactionapp.MutationBasisClaims, error) {
	return reactionapp.MutationBasisClaims{Identity: i, ExpectedVersion: ver, AllowedValues: []reactiondomain.Value{v}, AcceptUntil: time.Now().Add(time.Hour)}, nil
}
func (b testBasis) VerifyForRecovery(t string, i reactiondomain.Identity, v reactiondomain.Value, ver int64) (reactionapp.MutationBasisClaims, error) {
	return b.Verify(t, i, v, ver)
}
func (testBasis) Digest(string) string { return "test-basis-digest" }
func evidence(version int64) reactionapp.MutationEvidence {
	return reactionapp.MutationEvidence{MutationBasis: "test-basis", ExpectedVersion: version}
}
