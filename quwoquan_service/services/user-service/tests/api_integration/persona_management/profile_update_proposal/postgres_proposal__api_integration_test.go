package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalmodel "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	proposalpersistence "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestProfileUpdateProposalPostgresCreateReplayAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "proposal-owner", "proposal-persona"); err != nil {
			t.Fatal(err)
		}
		store, err := proposalpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		personaStore, err := personapersistence.NewProfileProposalPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		personaFacade, err := personaapp.NewProfileProposalFacade(personaStore)
		if err != nil {
			t.Fatal(err)
		}
		facade, err := proposalapp.NewFacade(store, store, personaFacade, personaStore)
		if err != nil {
			t.Fatal(err)
		}
		displayName := "待确认公开名称"
		command := proposalapp.CreateCommand{
			ProposalID: "profile-proposal-1", ActorPersonaID: "proposal-persona", TargetPersonaID: "proposal-persona",
			Source: proposalmodel.SourceAssistant, Changes: personamodel.ProfileChangeSet{DisplayName: &displayName},
			Reason: "用户可审核的画像建议", EvidenceRefs: []string{"assistant-run:run-1"}, ImpactScope: []string{"displayName"},
			IdempotencyKey: "proposal-create-key", RequestID: "proposal-request", TraceID: "proposal-trace",
		}
		first, err := facade.Create(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := facade.Create(ctx, command)
		if err != nil || !replayed.Replayed || replayed.Version != first.Version {
			t.Fatalf("ProfileUpdateProposal replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var stateCount, outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals WHERE proposal_id=$1`, command.ProposalID).Scan(&stateCount); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals_outbox WHERE aggregate_id=$1`, command.ProposalID).Scan(&outboxCount); err != nil {
			t.Fatal(err)
		}
		if stateCount != 1 || outboxCount != 1 {
			t.Fatalf("ProfileUpdateProposal packet mismatch: state=%d outbox=%d", stateCount, outboxCount)
		}
	})
}
