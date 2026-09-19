package local_contract

import (
	"context"
	"time"

	relapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type localBasis struct{}

func (localBasis) Issue(claims relapp.MutationBasisClaims) (string, error) { return "local-basis", nil }
func (localBasis) Verify(_ string, command relmodel.Command, pairID string) (relapp.MutationBasisClaims, error) {
	return relapp.MutationBasisClaims{ActorPersonaID: command.SourcePersonaID, TargetPersonaID: command.TargetPersonaID, PairID: pairID, ExpectedVersion: *command.ExpectedVersion, AcceptUntil: time.Now().Add(time.Hour)}, nil
}
func (b localBasis) VerifyForRecovery(token string, command relmodel.Command, pairID string) (relapp.MutationBasisClaims, error) {
	return b.Verify(token, command, pairID)
}
func (localBasis) Digest(string) string { return "local-digest" }

type localReceipts struct{}

func (localReceipts) Recover(context.Context, string, string, relmodel.CommandKind, string) (relmodel.MutationResult, bool, error) {
	return relmodel.MutationResult{}, false, nil
}
func (localReceipts) FinalizeExpired(context.Context, string, string, relmodel.CommandKind, string, time.Time) (relmodel.MutationResult, error) {
	return relmodel.MutationResult{Outcome: relmodel.OutcomeExpired}, nil
}
func localRelationshipOptions() []relapp.ServiceOption {
	return []relapp.ServiceOption{relapp.WithMutationBasis(localBasis{}, localReceipts{})}
}
func localEvidence(key string) relapp.CommandEvidence {
	return relapp.CommandEvidence{IdempotencyKey: key, MutationBasis: "local-basis", ExpectedVersion: 0}
}
