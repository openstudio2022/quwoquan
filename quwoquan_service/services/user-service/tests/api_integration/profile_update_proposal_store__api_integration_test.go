package api_integration

import (
	"context"
	"testing"

	personaapp "quwoquan_service/services/user-service/internal/application/persona/persona"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
	proposalmodel "quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
	personapersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/persona/persistence"
	proposalpersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/profile_update_proposal/persistence"
)

func TestProfileUpdateProposalPostgresCommitIsAtomicAndReplayable(t *testing.T) {
	cleanAll(t)
	store, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("new proposal store: %v", err)
	}
	ctx := context.Background()
	displayName := "商业提案"
	personaID := "persona-api-integration-1"
	createTestProfile(t, "proposal-owner-1", "提案 owner")
	createTestPersonaFull(t, "", "proposal-owner-1", personaID, "原始 Persona", "open", true)
	personaStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("new Persona Store: %v", err)
	}
	personaFacade, err := personaapp.NewProfileProposalFacade(personaStore)
	if err != nil {
		t.Fatalf("new Persona Facade: %v", err)
	}
	proposalFacade, err := proposalapp.NewFacade(store, store, personaFacade, personaStore)
	if err != nil {
		t.Fatalf("new proposal Facade: %v", err)
	}
	created, err := proposalFacade.Create(ctx, proposalapp.CreateCommand{
		ProposalID: "proposal-api-integration-1", ActorPersonaID: personaID,
		TargetPersonaID: personaID, Source: proposalmodel.SourceAssistant,
		Changes:        personamodel.ProfileChangeSet{DisplayName: &displayName},
		IdempotencyKey: "proposal-create-key",
	})
	if err != nil {
		t.Fatalf("create proposal through Facade: %v", err)
	}
	if created.Version != 1 || created.Status != string(proposalmodel.StatusPending) {
		t.Fatalf("unexpected create receipt: %#v", created)
	}

	confirmCommand := proposalapp.ConfirmCommand{
		ProposalID: "proposal-api-integration-1", ActorPersonaID: personaID,
		IdempotencyKey: "proposal-confirm-key",
	}
	confirmReceipt, err := proposalFacade.Confirm(ctx, confirmCommand)
	if err != nil {
		t.Fatalf("confirm proposal through PersonaVersionReader: %v", err)
	}
	if confirmReceipt.Version != 2 || confirmReceipt.Status != string(proposalmodel.StatusConfirmed) {
		t.Fatalf("unexpected confirm receipt: %#v", confirmReceipt)
	}
	replayedConfirm, err := proposalFacade.Confirm(ctx, confirmCommand)
	if err != nil || !replayedConfirm.Replayed {
		t.Fatalf("replay confirm mismatch: receipt=%#v err=%v", replayedConfirm, err)
	}
	noopConfirmCommand := proposalapp.ConfirmCommand{
		ProposalID: "proposal-api-integration-1", ActorPersonaID: personaID,
		IdempotencyKey: "proposal-confirm-noop-key",
	}
	noopConfirm, err := proposalFacade.Confirm(ctx, noopConfirmCommand)
	if err != nil || noopConfirm.Replayed || noopConfirm.Version != 2 {
		t.Fatalf("persist confirm no-op mismatch: receipt=%#v err=%v", noopConfirm, err)
	}
	confirmed, err := store.Load(ctx, "proposal-api-integration-1")
	if err != nil {
		t.Fatalf("load confirmed proposal: %v", err)
	}
	applied, err := proposalFacade.Apply(ctx, proposalapp.ApplyCommand{
		ProposalID: confirmed.ID, ActorPersonaID: personaID,
		IdempotencyKey: "proposal-apply-key",
	})
	if err != nil {
		t.Fatalf("apply proposal through Persona Command Facade: %v", err)
	}
	replayedApply, err := proposalFacade.Apply(ctx, proposalapp.ApplyCommand{
		ProposalID: confirmed.ID, ActorPersonaID: personaID,
		IdempotencyKey: "proposal-apply-key",
	})
	if err != nil {
		t.Fatalf("replay applied proposal: %v", err)
	}
	if applied.Status != string(proposalmodel.StatusApplied) || !replayedApply.Replayed {
		t.Fatalf("apply receipts mismatch: applied=%#v replayed=%#v", applied, replayedApply)
	}
	replayedNoopConfirm, err := proposalFacade.Confirm(ctx, noopConfirmCommand)
	if err != nil ||
		!replayedNoopConfirm.Replayed ||
		replayedNoopConfirm.Version != noopConfirm.Version ||
		replayedNoopConfirm.Status != noopConfirm.Status {
		t.Fatalf(
			"confirm no-op must replay the pre-apply result: receipt=%#v err=%v",
			replayedNoopConfirm,
			err,
		)
	}

	loaded, err := store.Load(ctx, confirmed.ID)
	if err != nil {
		t.Fatalf("load proposal: %v", err)
	}
	if loaded.Status != proposalmodel.StatusApplied || loaded.Version != 4 || loaded.ProposedChanges.DisplayName == nil || *loaded.ProposedChanges.DisplayName != displayName {
		t.Fatalf("loaded state mismatch: %#v", loaded)
	}

	var stateCount, receiptCount, outboxCount int
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals WHERE id=$1`, confirmed.ID).Scan(&stateCount); err != nil {
		t.Fatalf("count state: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals_command_receipts WHERE proposal_id=$1`, confirmed.ID).Scan(&receiptCount); err != nil {
		t.Fatalf("count receipts: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals_outbox WHERE aggregate_id=$1`, confirmed.ID).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if stateCount != 1 || receiptCount != 5 || outboxCount != 4 {
		t.Fatalf("atomic packet mismatch: state=%d receipts=%d outbox=%d", stateCount, receiptCount, outboxCount)
	}
	var (
		personaDisplayName string
		personaVersion     int64
		personaReceipts    int
		personaOutbox      int
	)
	if err := pgPool.QueryRow(ctx, `SELECT display_name, version FROM personas WHERE sub_account_id=$1`, personaID).Scan(&personaDisplayName, &personaVersion); err != nil {
		t.Fatalf("read applied Persona: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_command_receipts WHERE aggregate_id=$1`, personaID).Scan(&personaReceipts); err != nil {
		t.Fatalf("count Persona receipts: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1`, personaID).Scan(&personaOutbox); err != nil {
		t.Fatalf("count Persona outbox: %v", err)
	}
	if personaDisplayName != displayName || personaVersion != 2 || personaReceipts != 1 || personaOutbox != 1 {
		t.Fatalf("Persona packet mismatch: name=%q version=%d receipts=%d outbox=%d", personaDisplayName, personaVersion, personaReceipts, personaOutbox)
	}

	page, err := store.ListByPersona(ctx, confirmed.PersonaID, nil, 20)
	if err != nil {
		t.Fatalf("list proposal: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].ID != confirmed.ID || page.NextCursor != nil {
		t.Fatalf("unexpected proposal page: %#v", page)
	}
}
