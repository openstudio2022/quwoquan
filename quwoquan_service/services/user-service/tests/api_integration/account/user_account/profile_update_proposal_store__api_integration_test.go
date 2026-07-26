// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/spec.md#sit-001
package api_integration

import (
	"context"
	"testing"
	"time"

	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalmodel "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	proposalports "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
	proposalpersistence "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/persistence"
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

func TestProfileUpdateProposalRecoversApplyingCheckpointAfterResponseLoss(t *testing.T) {
	cleanAll(t)
	store, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("new proposal store: %v", err)
	}
	ctx := context.Background()
	const (
		ownerID    = "proposal-recovery-owner"
		personaID  = "persona-proposal-recovery"
		proposalID = "proposal-response-loss"
	)
	displayName := "恢复后的 Persona"
	createTestProfile(t, ownerID, "恢复提案 owner")
	createTestPersonaFull(t, "", ownerID, personaID, "原始 Persona", "open", true)
	personaStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("new persona proposal store: %v", err)
	}
	personaFacade, err := personaapp.NewProfileProposalFacade(personaStore)
	if err != nil {
		t.Fatalf("new Persona facade: %v", err)
	}
	proposalFacade, err := proposalapp.NewFacade(store, store, personaFacade, personaStore)
	if err != nil {
		t.Fatalf("new proposal facade: %v", err)
	}
	if _, err := proposalFacade.Create(ctx, proposalapp.CreateCommand{
		ProposalID: proposalID, ActorPersonaID: personaID, TargetPersonaID: personaID,
		Source:         proposalmodel.SourceAssistant,
		Changes:        personamodel.ProfileChangeSet{DisplayName: &displayName},
		IdempotencyKey: "response-loss-create",
	}); err != nil {
		t.Fatalf("create proposal: %v", err)
	}
	if _, err := proposalFacade.Confirm(ctx, proposalapp.ConfirmCommand{
		ProposalID: proposalID, ActorPersonaID: personaID,
		IdempotencyKey: "response-loss-confirm",
	}); err != nil {
		t.Fatalf("confirm proposal: %v", err)
	}

	confirmed, err := store.Load(ctx, proposalID)
	if err != nil {
		t.Fatalf("load confirmed proposal: %v", err)
	}
	applying, events, err := confirmed.BeginApply(time.Now().UTC())
	if err != nil {
		t.Fatalf("begin apply checkpoint: %v", err)
	}
	if _, err := store.Commit(ctx, confirmed.Version, proposalports.ChangeSet{
		Proposal:       applying,
		Events:         events,
		IdempotencyKey: "simulated-response-loss-claim",
		CommandDigest:  "simulated-response-loss-claim",
	}); err != nil {
		t.Fatalf("persist applying checkpoint: %v", err)
	}
	checkpoint, err := store.Load(ctx, proposalID)
	if err != nil {
		t.Fatalf("load durable applying checkpoint: %v", err)
	}
	if checkpoint.Status != proposalmodel.StatusApplying || checkpoint.Version != 3 {
		t.Fatalf("applying checkpoint=%#v, want durable applying version 3", checkpoint)
	}
	if err := personaFacade.ApplyProfileProposal(ctx, personaports.ApplyProfileProposalCommand{
		ProposalID:             proposalID,
		PersonaID:              personaID,
		ExpectedPersonaVersion: *applying.TargetPersonaExpectedVersion,
		Changes:                applying.ProposedChanges,
	}); err != nil {
		t.Fatalf("apply Persona before simulated response loss: %v", err)
	}

	// 新进程只有持久化 applying checkpoint 和 Persona 幂等 receipt；它必须能
	// 重放同一 Apply intent，而不是把提案留在 applying 或重复写 Persona。
	restartedPersonaFacade, err := personaapp.NewProfileProposalFacade(personaStore)
	if err != nil {
		t.Fatalf("restart Persona facade: %v", err)
	}
	restartedProposalFacade, err := proposalapp.NewFacade(
		store,
		store,
		restartedPersonaFacade,
		personaStore,
	)
	if err != nil {
		t.Fatalf("restart proposal facade: %v", err)
	}
	applyCommand := proposalapp.ApplyCommand{
		ProposalID: proposalID, ActorPersonaID: personaID,
		IdempotencyKey: "response-loss-apply",
	}
	recovered, err := restartedProposalFacade.Apply(ctx, applyCommand)
	if err != nil {
		t.Fatalf("resume applying proposal after response loss: %v", err)
	}
	if recovered.Status != string(proposalmodel.StatusApplied) || recovered.Replayed {
		t.Fatalf("recovered apply receipt=%#v, want first applied receipt", recovered)
	}
	replayed, err := restartedProposalFacade.Apply(ctx, applyCommand)
	if err != nil || !replayed.Replayed {
		t.Fatalf("replay recovered apply: receipt=%#v err=%v", replayed, err)
	}

	var (
		gotDisplayName  string
		personaVersion  int64
		personaReceipts int
	)
	if err := pgPool.QueryRow(
		ctx,
		`SELECT display_name, version FROM personas WHERE sub_account_id=$1`,
		personaID,
	).Scan(&gotDisplayName, &personaVersion); err != nil {
		t.Fatalf("load resumed Persona: %v", err)
	}
	if err := pgPool.QueryRow(
		ctx,
		`SELECT COUNT(*) FROM personas_command_receipts WHERE aggregate_id=$1`,
		personaID,
	).Scan(&personaReceipts); err != nil {
		t.Fatalf("count resumed Persona receipts: %v", err)
	}
	if gotDisplayName != displayName || personaVersion != 2 || personaReceipts != 1 {
		t.Fatalf(
			"response-loss resume rewrote Persona: name=%q version=%d receipts=%d",
			gotDisplayName,
			personaVersion,
			personaReceipts,
		)
	}
	loaded, err := store.Load(ctx, proposalID)
	if err != nil {
		t.Fatalf("load recovered proposal: %v", err)
	}
	if loaded.Status != proposalmodel.StatusApplied || loaded.Version != 4 {
		t.Fatalf("recovered proposal=%#v, want applied version 4", loaded)
	}
}
