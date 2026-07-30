// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-create-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalmodel "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	proposalports "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
	proposalmessaging "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/messaging"
	proposalpersistence "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/persistence"
)

func doProfileProposalPublicRequest(
	t *testing.T,
	method string,
	path string,
	body string,
	ownerID string,
	personaID string,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(
		"Authorization",
		authHeadersForPersona(ownerID, personaID)["Authorization"],
	)
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(operation.WithContext(
		request.Context(),
		operation.Context{
			RequestID: "request-" + idempotencyKey,
			TraceID:   "trace-" + idempotencyKey,
		},
	))
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	return recorder
}

func TestProfileUpdateProposalPublicCommandsExposeAuditableRollback(t *testing.T) {
	cleanAll(t)
	const (
		ownerID    = "proposal-http-owner"
		personaID  = "persona-proposal-http"
		proposalID = "proposal-http-1"
	)
	createTestProfile(t, ownerID, "公开提案 owner")
	createTestPersonaFull(t, "", ownerID, personaID, "回滚前身份", "open", true)
	created := doProfileProposalPublicRequest(
		t,
		http.MethodPost,
		"/user/personas/"+personaID+"/profile-proposals",
		`{"proposalId":"`+proposalID+`","source":"assistant","reason":"助手会话形成的可审核建议","evidenceRefs":["assistant-run:run-http-1"],"impactScope":["displayName"],"displayName":"回滚后新身份"}`,
		ownerID,
		personaID,
		"proposal-http-create",
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create public proposal: status=%d body=%s", created.Code, created.Body.String())
	}
	for _, command := range []struct {
		path string
		key  string
	}{
		{path: "/user/profile/proposals/" + proposalID + "/confirm", key: "proposal-http-confirm"},
		{path: "/user/profile/proposals/" + proposalID + "/apply", key: "proposal-http-apply"},
		{path: "/user/profile/proposals/" + proposalID + "/rollback", key: "proposal-http-rollback"},
	} {
		response := doProfileProposalPublicRequest(
			t,
			http.MethodPost,
			command.path,
			"",
			ownerID,
			personaID,
			command.key,
		)
		if response.Code != http.StatusOK {
			t.Fatalf("%s: status=%d body=%s", command.path, response.Code, response.Body.String())
		}
	}
	view := doProfileProposalPublicRequest(
		t,
		http.MethodGet,
		"/user/profile/proposals/"+proposalID,
		"",
		ownerID,
		personaID,
		"audit-read",
	)
	if view.Code != http.StatusOK {
		t.Fatalf("get public proposal: status=%d body=%s", view.Code, view.Body.String())
	}
	var payload struct {
		Status          string   `json:"status"`
		Reason          string   `json:"reason"`
		EvidenceRefs    []string `json:"evidenceRefs"`
		ImpactScope     []string `json:"impactScope"`
		ApplyAuditID    string   `json:"applyAuditId"`
		RollbackAuditID string   `json:"rollbackAuditId"`
	}
	if err := json.Unmarshal(view.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode public proposal: %v", err)
	}
	if payload.Status != string(proposalmodel.StatusRolledBack) ||
		payload.Reason == "" || len(payload.EvidenceRefs) != 1 ||
		len(payload.ImpactScope) != 1 || payload.ApplyAuditID == "" ||
		payload.RollbackAuditID == "" {
		t.Fatalf("public auditable proposal mismatch: %#v", payload)
	}
}

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
		Reason:         "根据助手会话更新公开身份",
		EvidenceRefs:   []string{"assistant-run:run-api-integration-1"},
		ImpactScope:    []string{"displayName"},
		IdempotencyKey: "proposal-create-key",
		RequestID:      "proposal-create-request", TraceID: "proposal-create-trace",
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
		RequestID:      "proposal-apply-request", TraceID: "proposal-apply-trace",
	})
	if err != nil {
		t.Fatalf("apply proposal through Persona Command Facade: %v", err)
	}
	replayedApply, err := proposalFacade.Apply(ctx, proposalapp.ApplyCommand{
		ProposalID: confirmed.ID, ActorPersonaID: personaID,
		IdempotencyKey: "proposal-apply-key",
		RequestID:      "proposal-apply-retry-request", TraceID: "proposal-apply-retry-trace",
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

	applyAudit, err := store.LoadAudit(ctx, confirmed.ID, proposalmodel.AuditActionApply)
	if err != nil {
		t.Fatalf("load immutable apply audit: %v", err)
	}
	if applyAudit.Before.DisplayName != "原始 Persona" ||
		applyAudit.After.DisplayName != displayName ||
		applyAudit.Context.RequestID != "proposal-apply-request" ||
		applyAudit.RollbackDeadline == nil {
		t.Fatalf("apply audit mismatch: %#v", applyAudit)
	}
	rollbackCommand := proposalapp.RollbackCommand{
		ProposalID: confirmed.ID, ActorPersonaID: personaID,
		IdempotencyKey: "proposal-rollback-key",
		RequestID:      "proposal-rollback-request", TraceID: "proposal-rollback-trace",
	}
	rolledBack, err := proposalFacade.Rollback(ctx, rollbackCommand)
	if err != nil {
		t.Fatalf("rollback proposal: %v", err)
	}
	replayedRollback, err := proposalFacade.Rollback(ctx, rollbackCommand)
	if err != nil || !replayedRollback.Replayed {
		t.Fatalf("replay rollback: receipt=%#v err=%v", replayedRollback, err)
	}
	if rolledBack.Status != string(proposalmodel.StatusRolledBack) {
		t.Fatalf("unexpected rollback receipt: %#v", rolledBack)
	}
	rollbackAudit, err := store.LoadAudit(ctx, confirmed.ID, proposalmodel.AuditActionRollback)
	if err != nil {
		t.Fatalf("load immutable rollback audit: %v", err)
	}
	if rollbackAudit.Before.DisplayName != displayName ||
		rollbackAudit.After.DisplayName != "原始 Persona" ||
		rollbackAudit.Context.TraceID != "proposal-rollback-trace" {
		t.Fatalf("rollback audit mismatch: %#v", rollbackAudit)
	}

	loaded, err := store.Load(ctx, confirmed.ID)
	if err != nil {
		t.Fatalf("load proposal: %v", err)
	}
	if loaded.Status != proposalmodel.StatusRolledBack || loaded.Version != 6 ||
		loaded.ProposedChanges.DisplayName == nil || *loaded.ProposedChanges.DisplayName != displayName ||
		loaded.Reason == "" || len(loaded.EvidenceRefs) != 1 ||
		loaded.ApplyAuditID == "" || loaded.RollbackAuditID == "" {
		t.Fatalf("loaded state mismatch: %#v", loaded)
	}

	var stateCount, receiptCount, outboxCount, auditCount int
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals WHERE id=$1`, confirmed.ID).Scan(&stateCount); err != nil {
		t.Fatalf("count state: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals_command_receipts WHERE proposal_id=$1`, confirmed.ID).Scan(&receiptCount); err != nil {
		t.Fatalf("count receipts: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals_outbox WHERE aggregate_id=$1`, confirmed.ID).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposal_audits WHERE proposal_id=$1`, confirmed.ID).Scan(&auditCount); err != nil {
		t.Fatalf("count audits: %v", err)
	}
	if stateCount != 1 || receiptCount != 7 || outboxCount != 6 || auditCount != 2 {
		t.Fatalf(
			"atomic packet mismatch: state=%d receipts=%d outbox=%d audits=%d",
			stateCount, receiptCount, outboxCount, auditCount,
		)
	}
	var (
		createdReason      string
		createdHasEvidence bool
		createdHasEnvelope bool
		appliedAuditID     string
		rollbackAuditID    string
	)
	if err := pgPool.QueryRow(ctx, `
SELECT payload_json->>'reason',
       payload_json ? 'evidenceRefs',
       payload_json ? 'proposal'
FROM profile_update_proposals_outbox
WHERE aggregate_id=$1 AND event_type='ProfileUpdateProposalCreated'`,
		confirmed.ID,
	).Scan(&createdReason, &createdHasEvidence, &createdHasEnvelope); err != nil {
		t.Fatalf("read created public event: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `
SELECT payload_json->>'applyAuditId'
FROM profile_update_proposals_outbox
WHERE aggregate_id=$1 AND event_type='ProfileUpdateProposalApplied'`,
		confirmed.ID,
	).Scan(&appliedAuditID); err != nil {
		t.Fatalf("read applied public event: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `
SELECT payload_json->>'rollbackAuditId'
FROM profile_update_proposals_outbox
WHERE aggregate_id=$1 AND event_type='ProfileUpdateProposalRolledBack'`,
		confirmed.ID,
	).Scan(&rollbackAuditID); err != nil {
		t.Fatalf("read rollback public event: %v", err)
	}
	if createdReason == "" || !createdHasEvidence || createdHasEnvelope ||
		appliedAuditID != loaded.ApplyAuditID || rollbackAuditID != loaded.RollbackAuditID {
		t.Fatalf(
			"public event contract mismatch: reason=%q evidence=%t envelope=%t applyAudit=%q rollbackAudit=%q",
			createdReason, createdHasEvidence, createdHasEnvelope,
			appliedAuditID, rollbackAuditID,
		)
	}
	var (
		personaDisplayName string
		personaVersion     int64
		personaReceipts    int
		personaOutbox      int
	)
	if err := pgPool.QueryRow(ctx, `SELECT display_name, version FROM personas WHERE persona_id=$1`, personaID).Scan(&personaDisplayName, &personaVersion); err != nil {
		t.Fatalf("read applied Persona: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_command_receipts WHERE aggregate_id=$1`, personaID).Scan(&personaReceipts); err != nil {
		t.Fatalf("count Persona receipts: %v", err)
	}
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1`, personaID).Scan(&personaOutbox); err != nil {
		t.Fatalf("count Persona outbox: %v", err)
	}
	if personaDisplayName != "原始 Persona" || personaVersion != 3 || personaReceipts != 2 || personaOutbox != 2 {
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
		Reason:         "响应丢失恢复测试",
		EvidenceRefs:   []string{"assistant-run:run-response-loss"},
		ImpactScope:    []string{"displayName"},
		IdempotencyKey: "response-loss-create",
		RequestID:      "response-loss-create-request", TraceID: "response-loss-create-trace",
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
	applyContext, err := proposalmodel.NewCommandAuditContext(
		personaID,
		"response-loss-original-apply-request",
		"response-loss-original-apply-trace",
	)
	if err != nil {
		t.Fatalf("build apply audit context: %v", err)
	}
	applying, events, err := confirmed.BeginApply(applyContext, time.Now().UTC())
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
	if _, err := personaFacade.ApplyProfileProposal(ctx, personaports.ApplyProfileProposalCommand{
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
		RequestID:      "response-loss-retry-request", TraceID: "response-loss-retry-trace",
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
		`SELECT display_name, version FROM personas WHERE persona_id=$1`,
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
	audit, err := store.LoadAudit(ctx, proposalID, proposalmodel.AuditActionApply)
	if err != nil {
		t.Fatalf("load recovered apply audit: %v", err)
	}
	if audit.Context.RequestID != "response-loss-original-apply-request" ||
		audit.Context.TraceID != "response-loss-original-apply-trace" {
		t.Fatalf("recovery replaced original apply attribution: %#v", audit.Context)
	}
}

func TestProfileUpdateProposalOutboxRelayPublishesInOrderAndReplaysAfterRestart(
	t *testing.T,
) {
	cleanAll(t)
	stopIntegrationRelayRunners()
	t.Cleanup(func() {
		if err := rebuildTestHandler(context.Background()); err != nil {
			t.Fatalf("restart integration relay runtime: %v", err)
		}
	})
	ctx := context.Background()
	if err := redisClient.Del(ctx, proposalmessaging.EventStream); err != nil {
		t.Fatalf("clear ProfileUpdateProposal stream: %v", err)
	}

	const (
		ownerID    = "proposal-relay-owner"
		personaID  = "persona-proposal-relay"
		proposalID = "proposal-relay-1"
	)
	createTestProfile(t, ownerID, "relay owner")
	createTestPersonaFull(t, "", ownerID, personaID, "relay before", "open", true)
	created := doProfileProposalPublicRequest(
		t,
		http.MethodPost,
		"/user/personas/"+personaID+"/profile-proposals",
		`{"proposalId":"`+proposalID+`","source":"assistant","reason":"relay contract","evidenceRefs":["assistant-run:relay"],"impactScope":["displayName"],"displayName":"relay after"}`,
		ownerID,
		personaID,
		"proposal-relay-create",
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create relay proposal: status=%d body=%s", created.Code, created.Body.String())
	}
	confirmed := doProfileProposalPublicRequest(
		t,
		http.MethodPost,
		"/user/profile/proposals/"+proposalID+"/confirm",
		"",
		ownerID,
		personaID,
		"proposal-relay-confirm",
	)
	if confirmed.Code != http.StatusOK {
		t.Fatalf(
			"confirm relay proposal: status=%d body=%s",
			confirmed.Code,
			confirmed.Body.String(),
		)
	}

	type storedEvent struct {
		id      string
		name    string
		payload string
	}
	rows, err := pgPool.Query(ctx, `
SELECT event_id, event_type, payload_json::text
FROM profile_update_proposals_outbox
WHERE aggregate_id=$1
ORDER BY aggregate_version`,
		proposalID,
	)
	if err != nil {
		t.Fatalf("list pending proposal events: %v", err)
	}
	var stored []storedEvent
	for rows.Next() {
		var event storedEvent
		if err := rows.Scan(&event.id, &event.name, &event.payload); err != nil {
			rows.Close()
			t.Fatalf("scan pending proposal event: %v", err)
		}
		stored = append(stored, event)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		t.Fatalf("iterate pending proposal events: %v", err)
	}
	rows.Close()
	if len(stored) != 2 ||
		stored[0].name != "ProfileUpdateProposalCreated" ||
		stored[1].name != "ProfileUpdateProposalConfirmed" {
		t.Fatalf("stored proposal event order=%#v", stored)
	}

	store, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("new proposal outbox store: %v", err)
	}
	claimedHead, err := store.ClaimPendingOutbox(
		ctx,
		"ordering-probe-1",
		time.Minute,
		100,
	)
	if err != nil || len(claimedHead) != 1 ||
		claimedHead[0].EventID != stored[0].id {
		t.Fatalf("claim ordered head=%#v err=%v", claimedHead, err)
	}
	blockedSuccessor, err := store.ClaimPendingOutbox(
		ctx,
		"ordering-probe-2",
		time.Minute,
		100,
	)
	if err != nil || len(blockedSuccessor) != 0 {
		t.Fatalf(
			"successor claimed before head checkpoint: events=%#v err=%v",
			blockedSuccessor,
			err,
		)
	}
	if err := store.ReleaseOutboxClaim(
		ctx,
		claimedHead[0].EventID,
		"ordering-probe-1",
	); err != nil {
		t.Fatalf("release ordered head probe: %v", err)
	}
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"user-service-api",
		runtimemessaging.RedisMessageTransportAdapter,
		redisClient,
		redisClient,
	)
	if err != nil {
		t.Fatalf("build real proposal message transport: %v", err)
	}
	eventPublisher := proposalmessaging.NewEventPublisher(transport)
	firstRelay, err := proposalapp.NewOutboxRelay(
		store,
		&failAfterProfileProposalAppend{
			delegate: eventPublisher,
			failOnce: true,
		},
	)
	if err != nil {
		t.Fatalf("new first proposal relay: %v", err)
	}
	if published, err := firstRelay.Drain(ctx, 100); err == nil || published != 0 {
		t.Fatalf(
			"first proposal drain=(%d, %v), want post-append acknowledgement loss",
			published,
			err,
		)
	}
	var (
		publishedCount int
		claimedCount   int
	)
	if err := pgPool.QueryRow(ctx, `
SELECT COUNT(*) FILTER (WHERE published_at IS NOT NULL),
       COUNT(*) FILTER (WHERE claim_owner IS NOT NULL)
FROM profile_update_proposals_outbox
WHERE aggregate_id=$1`,
		proposalID,
	).Scan(&publishedCount, &claimedCount); err != nil {
		t.Fatalf("read retained proposal checkpoint: %v", err)
	}
	if publishedCount != 0 || claimedCount != 0 {
		t.Fatalf(
			"publish failure advanced proposal outbox: published=%d claimed=%d",
			publishedCount,
			claimedCount,
		)
	}

	restartedRelay, err := proposalapp.NewOutboxRelay(store, eventPublisher)
	if err != nil {
		t.Fatalf("new restarted proposal relay: %v", err)
	}
	if published, err := restartedRelay.Drain(ctx, 100); err != nil || published != 1 {
		t.Fatalf("restart first ordered drain=(%d, %v), want one head event", published, err)
	}
	if published, err := restartedRelay.Drain(ctx, 100); err != nil || published != 1 {
		t.Fatalf("restart second ordered drain=(%d, %v), want successor", published, err)
	}
	if err := pgPool.QueryRow(ctx, `
SELECT COUNT(*)
FROM profile_update_proposals_outbox
WHERE aggregate_id=$1 AND published_at IS NOT NULL`,
		proposalID,
	).Scan(&publishedCount); err != nil {
		t.Fatalf("count published proposal checkpoints: %v", err)
	}
	if publishedCount != 2 {
		t.Fatalf("published checkpoints=%d, want 2", publishedCount)
	}

	group := "profile-proposal-relay-" + t.Name()
	if err := redisClient.XGroupCreateMkStream(
		ctx,
		proposalmessaging.EventStream,
		group,
		"0",
	); err != nil {
		t.Fatalf("create proposal relay consumer group: %v", err)
	}
	messages, err := redisClient.XReadGroup(
		ctx,
		group,
		"profile-proposal-relay-test",
		map[string]string{proposalmessaging.EventStream: ">"},
		10,
		3*time.Second,
	)
	if err != nil {
		t.Fatalf("read ProfileUpdateProposal stream: %v", err)
	}
	if len(messages) != 3 {
		t.Fatalf("stream messages=%d, want replay duplicate plus successor", len(messages))
	}
	wantNames := []string{
		"ProfileUpdateProposalCreated",
		"ProfileUpdateProposalCreated",
		"ProfileUpdateProposalConfirmed",
	}
	wantIDs := []string{stored[0].id, stored[0].id, stored[1].id}
	wantPayloads := []string{stored[0].payload, stored[0].payload, stored[1].payload}
	for index, message := range messages {
		if message.Values["eventName"] != wantNames[index] ||
			message.Values["eventId"] != wantIDs[index] ||
			message.Values["proposalId"] != proposalID ||
			message.Values["payload"] != wantPayloads[index] {
			t.Fatalf("stream message[%d]=%#v", index, message.Values)
		}
	}
}

type failAfterProfileProposalAppend struct {
	delegate *proposalmessaging.EventPublisher
	failOnce bool
}

func (publisher *failAfterProfileProposalAppend) PublishProfileUpdateProposal(
	ctx context.Context,
	event proposalports.OutboxEvent,
) error {
	if err := publisher.delegate.PublishProfileUpdateProposal(ctx, event); err != nil {
		return err
	}
	if publisher.failOnce {
		publisher.failOnce = false
		return errors.New("simulated post-append acknowledgement loss")
	}
	return nil
}
