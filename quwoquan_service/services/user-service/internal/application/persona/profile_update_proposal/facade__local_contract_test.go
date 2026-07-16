package profile_update_proposal

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
	personaports "quwoquan_service/services/user-service/internal/domain/persona/persona/ports"
	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/ports"
)

type receiptRecord struct {
	digest  string
	receipt ports.CommitReceipt
}

type memoryProposalStore struct {
	proposals map[string]model.ProfileUpdateProposal
	receipts  map[string]receiptRecord
}

func newMemoryProposalStore() *memoryProposalStore {
	return &memoryProposalStore{
		proposals: map[string]model.ProfileUpdateProposal{},
		receipts:  map[string]receiptRecord{},
	}
}

func (s *memoryProposalStore) Load(_ context.Context, id string) (model.ProfileUpdateProposal, error) {
	proposal, ok := s.proposals[id]
	if !ok {
		return model.ProfileUpdateProposal{}, model.ErrNotFound
	}
	return proposal, nil
}

func (s *memoryProposalStore) Get(ctx context.Context, id string) (model.ProfileUpdateProposal, error) {
	return s.Load(ctx, id)
}

func (s *memoryProposalStore) ListByPersona(_ context.Context, personaID string, _ *ports.Cursor, limit int) (ports.Slice, error) {
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

func receiptKey(proposalID, idempotencyKey string) string {
	return proposalID + "\x00" + idempotencyKey
}

func (s *memoryProposalStore) Replay(_ context.Context, proposalID, idempotencyKey, digest string) (ports.CommitReceipt, bool, error) {
	record, ok := s.receipts[receiptKey(proposalID, idempotencyKey)]
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

func (s *memoryProposalStore) Commit(_ context.Context, expectedVersion int64, changes ports.ChangeSet) (ports.CommitReceipt, error) {
	current, exists := s.proposals[changes.Proposal.ID]
	if (!exists && expectedVersion != 0) || (exists && current.Version != expectedVersion) {
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	if changes.Proposal.Version != expectedVersion+1 || len(changes.Events) != 1 {
		return ports.CommitReceipt{}, fmt.Errorf("invalid change set")
	}
	key := receiptKey(changes.Proposal.ID, changes.IdempotencyKey)
	if record, ok := s.receipts[key]; ok {
		if record.digest != changes.CommandDigest {
			return ports.CommitReceipt{}, model.ErrIdempotencyConflict
		}
		receipt := record.receipt
		receipt.Replayed = true
		return receipt, nil
	}
	s.proposals[changes.Proposal.ID] = changes.Proposal
	receipt := ports.CommitReceipt{
		ProposalID: changes.Proposal.ID,
		Version:    changes.Proposal.Version,
		Status:     string(changes.Proposal.Status),
	}
	s.receipts[key] = receiptRecord{digest: changes.CommandDigest, receipt: receipt}
	return receipt, nil
}

type recordingPersonaWriter struct {
	calls     int
	version   int64
	proposals map[string]personaports.ApplyProfileProposalCommand
}

func (w *recordingPersonaWriter) CurrentVersion(_ context.Context, _ string) (int64, error) {
	return w.version, nil
}

func (w *recordingPersonaWriter) ApplyProfileProposal(_ context.Context, command personaports.ApplyProfileProposalCommand) error {
	if previous, ok := w.proposals[command.ProposalID]; ok {
		if previous.PersonaID != command.PersonaID || previous.ExpectedPersonaVersion != command.ExpectedPersonaVersion {
			return model.ErrIdempotencyConflict
		}
		return nil
	}
	w.calls++
	w.proposals[command.ProposalID] = command
	return nil
}

func TestFacadeOwnerVersionAndIdempotentApply(t *testing.T) {
	t.Parallel()
	store := newMemoryProposalStore()
	writer := &recordingPersonaWriter{version: 8, proposals: map[string]personaports.ApplyProfileProposalCommand{}}
	facade, err := NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	now := time.Date(2026, 7, 16, 8, 0, 0, 0, time.UTC)
	facade.now = func() time.Time {
		now = now.Add(time.Second)
		return now
	}
	displayName := "new name"
	create := CreateCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-1", TargetPersonaID: "persona-1",
		Source: model.SourcePersona, Changes: personamodel.ProfileChangeSet{DisplayName: &displayName},
		IdempotencyKey: "create-1",
	}
	if _, err := facade.Create(context.Background(), create); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-2", ExpectedProposalVersion: 1,
		IdempotencyKey: "confirm-wrong-owner",
	}); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("foreign actor was not denied: %v", err)
	}
	if _, err := facade.Confirm(context.Background(), ConfirmCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-1", ExpectedProposalVersion: 1,
		IdempotencyKey: "confirm-1",
	}); err != nil {
		t.Fatalf("confirm: %v", err)
	}
	apply := ApplyCommand{
		ProposalID: "proposal-1", ActorPersonaID: "persona-1",
		ExpectedProposalVersion: 2, IdempotencyKey: "apply-1",
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
	if _, err := facade.Get(context.Background(), "proposal-1", "persona-2"); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("foreign reader was not denied: %v", err)
	}
	if _, err := facade.ListByPersona(context.Background(), "persona-1", "persona-2", nil, 20); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("foreign list reader was not denied: %v", err)
	}
}
