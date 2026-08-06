// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-create-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/spec.md#sit-001
// readiness_case: create-profile-update-proposal-local
// readiness_case: confirm-profile-update-proposal-local
// readiness_case: apply-profile-update-proposal-local
// readiness_case: reject-profile-update-proposal-local
// readiness_case: rollback-profile-update-proposal-local
// readiness_case: get-profile-update-proposal-local
// readiness_case: list-profile-update-proposals-local
package local_contract

import (
	"context"
	"errors"
	"fmt"
	. "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	"testing"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
)

type migratedFacadeReceiptRecord struct {
	digest  string
	receipt ports.CommitReceipt
}

type migratedFacadeMemoryProposalStore struct {
	proposals map[string]model.ProfileUpdateProposal
	receipts  map[string]migratedFacadeReceiptRecord
	audits    map[string]model.AuditRecord
}

func migratedFacadeNewMemoryProposalStore() *migratedFacadeMemoryProposalStore {
	return &migratedFacadeMemoryProposalStore{
		proposals: map[string]model.ProfileUpdateProposal{},
		receipts:  map[string]migratedFacadeReceiptRecord{},
		audits:    map[string]model.AuditRecord{},
	}
}

func (s *migratedFacadeMemoryProposalStore) Load(_ context.Context, id string) (model.ProfileUpdateProposal, error) {
	proposal, ok := s.proposals[id]
	if !ok {
		return model.ProfileUpdateProposal{}, model.ErrNotFound
	}
	return proposal, nil
}

func (s *migratedFacadeMemoryProposalStore) Get(ctx context.Context, id string) (model.ProfileUpdateProposal, error) {
	return s.Load(ctx, id)
}

func (s *migratedFacadeMemoryProposalStore) LoadAudit(
	_ context.Context,
	proposalID string,
	action model.AuditAction,
) (model.AuditRecord, error) {
	audit, ok := s.audits[proposalID+"\x00"+string(action)]
	if !ok {
		return model.AuditRecord{}, model.ErrNotFound
	}
	return audit, nil
}

func (s *migratedFacadeMemoryProposalStore) ListByPersona(_ context.Context, personaID string, _ *ports.Cursor, limit int) (ports.Slice, error) {
	result := ports.Slice{}
	for _, proposal := range s.proposals {
		if proposal.PersonaID == personaID {
			result.Items = append(result.Items, proposal)
			if len(result.Items) == limit {
				break
			}
		}
	}
	return result, nil
}

func migratedFacadeReceiptKey(actorPersonaID, idempotencyKey string) string {
	return actorPersonaID + "\x00" + idempotencyKey
}

func (s *migratedFacadeMemoryProposalStore) Replay(_ context.Context, actorPersonaID, idempotencyKey, digest string) (ports.CommitReceipt, bool, error) {
	record, ok := s.receipts[migratedFacadeReceiptKey(actorPersonaID, idempotencyKey)]
	if !ok {
		return ports.CommitReceipt{}, false, nil
	}
	if record.digest != digest {
		return ports.CommitReceipt{}, false, model.ErrIdempotencyConflict
	}
	receipt := record.receipt
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *migratedFacadeMemoryProposalStore) RecordNoopReceipt(
	_ context.Context,
	proposal model.ProfileUpdateProposal,
	idempotencyKey string,
	digest string,
) (ports.CommitReceipt, error) {
	key := migratedFacadeReceiptKey(proposal.PersonaID, idempotencyKey)
	if record, ok := s.receipts[key]; ok {
		if record.digest != digest {
			return ports.CommitReceipt{}, model.ErrIdempotencyConflict
		}
		receipt := record.receipt
		receipt.Replayed = true
		return receipt, nil
	}
	receipt := ports.CommitReceipt{
		ProposalID: proposal.ID,
		Version:    proposal.Version,
		Status:     string(proposal.Status),
	}
	s.receipts[key] = migratedFacadeReceiptRecord{digest: digest, receipt: receipt}
	return receipt, nil
}

func (s *migratedFacadeMemoryProposalStore) Commit(_ context.Context, expectedVersion int64, changes ports.ChangeSet) (ports.CommitReceipt, error) {
	current, exists := s.proposals[changes.Proposal.ID]
	if (!exists && expectedVersion != 0) || (exists && current.Version != expectedVersion) {
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	if changes.Proposal.Version != expectedVersion+1 || len(changes.Events) != 1 {
		return ports.CommitReceipt{}, fmt.Errorf("invalid change set")
	}
	key := migratedFacadeReceiptKey(changes.Proposal.PersonaID, changes.IdempotencyKey)
	if record, ok := s.receipts[key]; ok {
		if record.digest != changes.CommandDigest {
			return ports.CommitReceipt{}, model.ErrIdempotencyConflict
		}
		receipt := record.receipt
		receipt.Replayed = true
		return receipt, nil
	}
	s.proposals[changes.Proposal.ID] = changes.Proposal
	if changes.Audit != nil {
		s.audits[changes.Proposal.ID+"\x00"+string(changes.Audit.Action)] = *changes.Audit
	}
	receipt := ports.CommitReceipt{
		ProposalID: changes.Proposal.ID,
		Version:    changes.Proposal.Version,
		Status:     string(changes.Proposal.Status),
	}
	s.receipts[key] = migratedFacadeReceiptRecord{digest: changes.CommandDigest, receipt: receipt}
	return receipt, nil
}

type migratedFacadeRecordingPersonaWriter struct {
	calls         int
	rollbackCalls int
	version       int64
	snapshot      personamodel.ProfileSnapshot
	proposals     map[string]personaports.ApplyProfileProposalCommand
	mutations     map[string]personaports.ProfileProposalMutationResult
	rollbacks     map[string]personaports.ProfileProposalMutationResult
	beforeApply   func()
	applyErr      error
}

func migratedFacadeNewPersonaWriter(version int64) *migratedFacadeRecordingPersonaWriter {
	return &migratedFacadeRecordingPersonaWriter{
		version:   version,
		snapshot:  personamodel.ProfileSnapshot{DisplayName: "old name", IsolationLevel: "open", Version: version},
		proposals: map[string]personaports.ApplyProfileProposalCommand{},
		mutations: map[string]personaports.ProfileProposalMutationResult{},
		rollbacks: map[string]personaports.ProfileProposalMutationResult{},
	}
}

func migratedFacadeCreateCommand(
	proposalID string,
	personaID string,
	changes personamodel.ProfileChangeSet,
	idempotencyKey string,
) CreateCommand {
	return CreateCommand{
		ProposalID: proposalID, ActorPersonaID: personaID, TargetPersonaID: personaID,
		Source: model.SourcePersona, Changes: changes,
		Reason:         "用户确认的资料优化",
		EvidenceRefs:   []string{"assistant-run:run-1"},
		ImpactScope:    changes.ChangedFields(),
		IdempotencyKey: idempotencyKey,
		RequestID:      "request-" + idempotencyKey,
		TraceID:        "trace-" + idempotencyKey,
	}
}

func (w *migratedFacadeRecordingPersonaWriter) CurrentVersion(_ context.Context, _ string) (int64, error) {
	return w.version, nil
}

func (w *migratedFacadeRecordingPersonaWriter) ApplyProfileProposal(
	_ context.Context,
	command personaports.ApplyProfileProposalCommand,
) (personaports.ProfileProposalMutationResult, error) {
	if w.beforeApply != nil {
		w.beforeApply()
		w.beforeApply = nil
	}
	if w.applyErr != nil {
		return personaports.ProfileProposalMutationResult{}, w.applyErr
	}
	if previous, ok := w.proposals[command.ProposalID]; ok {
		if previous.PersonaID != command.PersonaID || previous.ExpectedPersonaVersion != command.ExpectedPersonaVersion {
			return personaports.ProfileProposalMutationResult{}, model.ErrIdempotencyConflict
		}
		return w.mutations[command.ProposalID], nil
	}
	if w.snapshot.Version == 0 {
		w.snapshot = personamodel.ProfileSnapshot{
			DisplayName: "old name", IsolationLevel: "open", Version: w.version,
		}
	}
	before := w.snapshot
	after := before
	if command.Changes.DisplayName != nil {
		after.DisplayName = *command.Changes.DisplayName
	}
	after.Version = before.Version + 1
	mutation := personaports.ProfileProposalMutationResult{
		Before: before, After: after,
		OccurredAt: time.Now().UTC(),
	}
	w.calls++
	w.proposals[command.ProposalID] = command
	w.mutations[command.ProposalID] = mutation
	w.snapshot = after
	w.version = after.Version
	return mutation, nil
}

func (w *migratedFacadeRecordingPersonaWriter) RollbackProfileProposal(
	_ context.Context,
	command personaports.RollbackProfileProposalCommand,
) (personaports.ProfileProposalMutationResult, error) {
	if result, ok := w.rollbacks[command.ProposalID]; ok {
		return result, nil
	}
	if w.snapshot.Version != command.ExpectedPersonaVersion {
		return personaports.ProfileProposalMutationResult{}, personamodel.ErrVersionConflict
	}
	before := w.snapshot
	after := command.Snapshot
	after.Version = before.Version + 1
	result := personaports.ProfileProposalMutationResult{
		Before: before, After: after,
		OccurredAt: time.Now().UTC(),
	}
	w.rollbackCalls++
	w.rollbacks[command.ProposalID] = result
	w.snapshot = after
	w.version = after.Version
	return result, nil
}

func TestFacadeOwnerAndIdempotentApply(t *testing.T) {
	t.Parallel()
	store := migratedFacadeNewMemoryProposalStore()
	writer := migratedFacadeNewPersonaWriter(8)
	facade, err := NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	displayName := "new name"
	create := migratedFacadeCreateCommand(
		"proposal-1",
		"persona-1",
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"create-1",
	)
	firstCreate, err := facade.Create(context.Background(), create)
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	retryCreate := create
	retryCreate.RequestID = "request-create-retry"
	retryCreate.TraceID = "trace-create-retry"
	replayedCreate, err := facade.Create(context.Background(), retryCreate)
	if err != nil || !replayedCreate.Replayed ||
		replayedCreate.ProposalID != firstCreate.ProposalID {
		t.Fatalf("create replay mismatch: first=%+v replay=%+v err=%v", firstCreate, replayedCreate, err)
	}
	conflictingCreate := retryCreate
	conflictingCreate.Reason = "不同 intent"
	if _, err := facade.Create(context.Background(), conflictingCreate); !errors.Is(
		err,
		model.ErrIdempotencyConflict,
	) {
		t.Fatalf("create idempotency conflict was not enforced: %v", err)
	}
	conflictingProposalID := retryCreate
	conflictingProposalID.ProposalID = "proposal-2"
	if _, err := facade.Create(context.Background(), conflictingProposalID); !errors.Is(
		err,
		model.ErrIdempotencyConflict,
	) {
		t.Fatalf("actor-scoped create key allowed a second proposal: %v", err)
	}
	createdProposal, err := store.Load(context.Background(), "proposal-1")
	if err != nil || createdProposal.Reason != create.Reason ||
		len(createdProposal.EvidenceRefs) != 1 ||
		createdProposal.CreatedRequestID != create.RequestID {
		t.Fatalf("auditable creation mismatch: proposal=%+v err=%v", createdProposal, err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-2",
		IdempotencyKey: "confirm-wrong-owner",
	}); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("foreign actor was not denied: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-1",
	}); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	apply := ApplyCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-1",
		IdempotencyKey: "apply-1", RequestID: "request-apply-1", TraceID: "trace-apply-1",
	}
	first, err := facade.Apply(context.Background(), apply)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	second, err := facade.Apply(context.Background(), apply)
	if err != nil {
		t.Fatalf("replay apply: %v", err)
	}
	if first.Status != string(model.StatusApplied) || !second.Replayed || writer.calls != 1 {
		t.Fatalf("apply replay mismatch: first=%#v second=%#v writerCalls=%d", first, second, writer.calls)
	}
	rollback := RollbackCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-1",
		IdempotencyKey: "rollback-1", RequestID: "request-rollback-1",
		TraceID: "trace-rollback-1",
	}
	rolledBack, err := facade.Rollback(context.Background(), rollback)
	if err != nil {
		t.Fatalf("rollback: %v", err)
	}
	replayedRollback, err := facade.Rollback(context.Background(), rollback)
	if err != nil {
		t.Fatalf("replay rollback: %v", err)
	}
	if rolledBack.Status != string(model.StatusRolledBack) ||
		!replayedRollback.Replayed || writer.rollbackCalls != 1 {
		t.Fatalf(
			"rollback replay mismatch: first=%#v replay=%#v calls=%d",
			rolledBack,
			replayedRollback,
			writer.rollbackCalls,
		)
	}
	if _, err := store.LoadAudit(context.Background(), "proposal-1", model.AuditActionApply); err != nil {
		t.Fatalf("load apply audit: %v", err)
	}
	if _, err := store.LoadAudit(context.Background(), "proposal-1", model.AuditActionRollback); err != nil {
		t.Fatalf("load rollback audit: %v", err)
	}
	owned, err := facade.Get(context.Background(), "proposal-1", "persona-1")
	if err != nil || owned.Status != model.StatusRolledBack {
		t.Fatalf("owned GetProfileUpdateProposal: value=%+v err=%v", owned, err)
	}
	ownedSlice, err := facade.ListByPersona(
		context.Background(), "persona-1", "persona-1", nil, 20,
	)
	if err != nil || len(ownedSlice.Items) != 1 || ownedSlice.Items[0].ID != "proposal-1" {
		t.Fatalf("owned ListProfileUpdateProposals: value=%+v err=%v", ownedSlice, err)
	}
	if _, err := facade.Get(context.Background(), "proposal-1", "persona-2"); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("foreign reader was not denied: %v", err)
	}
	if _, err := facade.ListByPersona(context.Background(), "persona-1", "persona-2", nil, 20); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("foreign list reader was not denied: %v", err)
	}
}

func TestFacadeNoopIntentReplaysOriginalReceiptAfterStateAdvances(t *testing.T) {
	t.Parallel()
	store := migratedFacadeNewMemoryProposalStore()
	writer := migratedFacadeNewPersonaWriter(8)
	facade, err := NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	displayName := "new name"
	if _, err := facade.Create(context.Background(), migratedFacadeCreateCommand(
		"proposal-noop-receipt",
		"persona-1",
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"create-noop-receipt",
	)); err != nil {
		t.Fatalf("create proposal: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID:     "proposal-noop-receipt",
		ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-first",
	}); err != nil {
		t.Fatalf("confirm proposal: %v", err)
	}
	noopCommand := ConfirmCommand{
		ProposalID:     "proposal-noop-receipt",
		ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-noop",
	}
	noop, err := facade.Confirm(context.Background(), noopCommand)
	if err != nil {
		t.Fatalf("record confirm no-op: %v", err)
	}
	if noop.Replayed || noop.Version != 2 || noop.Status != string(model.StatusConfirmed) {
		t.Fatalf("first no-op must persist confirmed receipt: %+v", noop)
	}
	if _, err := facade.Apply(context.Background(), ApplyCommand{
		ProposalID:     "proposal-noop-receipt",
		ActorPersonaID: "persona-1",
		IdempotencyKey: "apply-after-noop",
		RequestID:      "request-apply-after-noop", TraceID: "trace-apply-after-noop",
	}); err != nil {
		t.Fatalf("apply proposal: %v", err)
	}
	replayed, err := facade.Confirm(context.Background(), noopCommand)
	if err != nil {
		t.Fatalf("replay confirm no-op: %v", err)
	}
	if !replayed.Replayed ||
		replayed.Version != noop.Version ||
		replayed.Status != noop.Status {
		t.Fatalf("no-op retry must replay the original result: %+v", replayed)
	}
	current, err := store.Load(context.Background(), "proposal-noop-receipt")
	if err != nil || current.Status != model.StatusApplied || current.Version != 4 {
		t.Fatalf(
			"no-op replay must not overwrite the applied proposal: proposal=%+v err=%v",
			current,
			err,
		)
	}
}

func TestFacadeApplyClaimBlocksConcurrentReject(t *testing.T) {
	t.Parallel()
	store := migratedFacadeNewMemoryProposalStore()
	writer := migratedFacadeNewPersonaWriter(8)
	facade, err := NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	displayName := "claimed name"
	if _, err := facade.Create(context.Background(), migratedFacadeCreateCommand(
		"proposal-race",
		"persona-1",
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"create-race",
	)); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-race", ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-race",
	}); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	var rejectErr error
	writer.beforeApply = func() {
		_, rejectErr = facade.Reject(context.Background(), RejectCommand{
			ProposalID: "proposal-race", ActorPersonaID: "persona-1",
			IdempotencyKey: "reject-race",
		})
	}
	applied, err := facade.Apply(context.Background(), ApplyCommand{
		ProposalID: "proposal-race", ActorPersonaID: "persona-1",
		IdempotencyKey: "apply-race", RequestID: "request-apply-race", TraceID: "trace-apply-race",
	})
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if !errors.Is(rejectErr, model.ErrInvalidTransition) {
		t.Fatalf("reject crossed durable apply claim: %v", rejectErr)
	}
	if applied.Status != string(model.StatusApplied) || writer.calls != 1 {
		t.Fatalf("unexpected applied receipt=%+v writerCalls=%d", applied, writer.calls)
	}
}

func TestFacadeExpiresClaimWhenPersonaSnapshotIsStale(t *testing.T) {
	t.Parallel()
	store := migratedFacadeNewMemoryProposalStore()
	writer := migratedFacadeNewPersonaWriter(8)
	writer.applyErr = personamodel.ErrVersionConflict
	facade, err := NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	displayName := "stale name"
	if _, err := facade.Create(context.Background(), migratedFacadeCreateCommand(
		"proposal-stale",
		"persona-1",
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"create-stale",
	)); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-stale", ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-stale",
	}); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	if _, err := facade.Apply(context.Background(), ApplyCommand{
		ProposalID: "proposal-stale", ActorPersonaID: "persona-1",
		IdempotencyKey: "apply-stale", RequestID: "request-apply-stale", TraceID: "trace-apply-stale",
	}); !errors.Is(err, personamodel.ErrVersionConflict) {
		t.Fatalf("stale Persona snapshot error=%v", err)
	}
	proposal, err := store.Load(context.Background(), "proposal-stale")
	if err != nil {
		t.Fatalf("load expired proposal: %v", err)
	}
	if proposal.Status != model.StatusExpired || proposal.ResolvedAt == nil {
		t.Fatalf("stale apply did not expire claim: %+v", proposal)
	}
}

func TestFacadeRollbackRefusesInterveningPersonaVersionAndRestoresAppliedState(t *testing.T) {
	t.Parallel()
	store := migratedFacadeNewMemoryProposalStore()
	writer := migratedFacadeNewPersonaWriter(8)
	facade, err := NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	displayName := "applied name"
	if _, err := facade.Create(context.Background(), migratedFacadeCreateCommand(
		"proposal-rollback-conflict",
		"persona-1",
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"create-rollback-conflict",
	)); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-rollback-conflict", ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-rollback-conflict",
	}); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	if _, err := facade.Apply(context.Background(), ApplyCommand{
		ProposalID: "proposal-rollback-conflict", ActorPersonaID: "persona-1",
		IdempotencyKey: "apply-rollback-conflict",
		RequestID:      "request-apply-rollback-conflict",
		TraceID:        "trace-apply-rollback-conflict",
	}); err != nil {
		t.Fatalf("apply: %v", err)
	}

	// Simulate an independent Persona command after apply. Controlled rollback
	// must not overwrite that newer state.
	writer.snapshot.Version++
	writer.version = writer.snapshot.Version
	if _, err := facade.Rollback(context.Background(), RollbackCommand{
		ProposalID: "proposal-rollback-conflict", ActorPersonaID: "persona-1",
		IdempotencyKey: "rollback-conflict",
		RequestID:      "request-rollback-conflict", TraceID: "trace-rollback-conflict",
	}); !errors.Is(err, personamodel.ErrVersionConflict) {
		t.Fatalf("intervening Persona version was overwritten: %v", err)
	}
	proposal, err := store.Load(context.Background(), "proposal-rollback-conflict")
	if err != nil {
		t.Fatalf("load proposal: %v", err)
	}
	if proposal.Status != model.StatusApplied || proposal.RollbackContext != nil ||
		proposal.RollbackAuditID != "" || writer.rollbackCalls != 0 {
		t.Fatalf("rollback conflict left partial state: proposal=%+v calls=%d", proposal, writer.rollbackCalls)
	}
}
