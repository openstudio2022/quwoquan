package profile_update_proposal

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
	personaports "quwoquan_service/services/user-service/internal/domain/persona/persona/ports"
	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/ports"
)

type Facade struct {
	store         ports.AggregateStore
	reader        ports.Reader
	personaWriter personaports.ProfileProposalCommandFacade
	personaReader personaports.ProfileProposalVersionReader
	now           func() time.Time
}

func NewFacade(
	store ports.AggregateStore,
	reader ports.Reader,
	personaWriter personaports.ProfileProposalCommandFacade,
	personaReader personaports.ProfileProposalVersionReader,
) (*Facade, error) {
	if store == nil || reader == nil || personaWriter == nil || personaReader == nil {
		return nil, errors.New("profile proposal Store, Reader and Persona command/query Facades are required")
	}
	return &Facade{
		store: store, reader: reader, personaWriter: personaWriter,
		personaReader: personaReader, now: time.Now,
	}, nil
}

type CreateCommand struct {
	ProposalID      string
	ActorPersonaID  string
	TargetPersonaID string
	Source          model.Source
	Changes         personamodel.ProfileChangeSet
	IdempotencyKey  string
}

type ConfirmCommand struct {
	ProposalID              string
	ActorPersonaID          string
	ExpectedProposalVersion int64
	IdempotencyKey          string
}

type ApplyCommand struct {
	ProposalID              string
	ActorPersonaID          string
	ExpectedProposalVersion int64
	IdempotencyKey          string
}

type RejectCommand struct {
	ProposalID              string
	ActorPersonaID          string
	ExpectedProposalVersion int64
	IdempotencyKey          string
}

func (f *Facade) Create(ctx context.Context, command CreateCommand) (ports.CommitReceipt, error) {
	if strings.TrimSpace(command.ActorPersonaID) == "" || command.ActorPersonaID != command.TargetPersonaID {
		return ports.CommitReceipt{}, model.ErrForbidden
	}
	digest, err := commandDigest(command)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := f.store.Replay(ctx, command.ProposalID, command.IdempotencyKey, digest); err != nil || found {
		return receipt, err
	}
	proposal, events, err := model.NewProfileUpdateProposal(
		command.ProposalID,
		command.TargetPersonaID,
		command.Source,
		command.Changes,
		f.now(),
	)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	return f.store.Commit(ctx, 0, ports.ChangeSet{
		Proposal: proposal, Events: events, IdempotencyKey: command.IdempotencyKey,
		CommandDigest: digest,
	})
}

func (f *Facade) Confirm(ctx context.Context, command ConfirmCommand) (ports.CommitReceipt, error) {
	digest, err := commandDigest(command)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := f.store.Replay(ctx, command.ProposalID, command.IdempotencyKey, digest); err != nil || found {
		return receipt, err
	}
	proposal, err := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if proposal.Version != command.ExpectedProposalVersion {
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	targetVersion, err := f.personaReader.CurrentVersion(ctx, proposal.PersonaID)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	next, events, err := proposal.Confirm(
		command.ActorPersonaID,
		targetVersion,
		f.now(),
	)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	return f.commit(ctx, command.ExpectedProposalVersion, next, events, command.IdempotencyKey, digest)
}

func (f *Facade) Apply(ctx context.Context, command ApplyCommand) (ports.CommitReceipt, error) {
	digest, err := commandDigest(command)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := f.store.Replay(ctx, command.ProposalID, command.IdempotencyKey, digest); err != nil || found {
		return receipt, err
	}
	proposal, err := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if proposal.Version != command.ExpectedProposalVersion || proposal.TargetPersonaExpectedVersion == nil {
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	if err := f.personaWriter.ApplyProfileProposal(ctx, personaports.ApplyProfileProposalCommand{
		ProposalID:             proposal.ID,
		PersonaID:              proposal.PersonaID,
		ExpectedPersonaVersion: *proposal.TargetPersonaExpectedVersion,
		Changes:                proposal.ProposedChanges,
	}); err != nil {
		return ports.CommitReceipt{}, err
	}
	next, events, err := proposal.MarkApplied(f.now())
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	return f.commit(ctx, command.ExpectedProposalVersion, next, events, command.IdempotencyKey, digest)
}

func (f *Facade) Reject(ctx context.Context, command RejectCommand) (ports.CommitReceipt, error) {
	digest, err := commandDigest(command)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := f.store.Replay(ctx, command.ProposalID, command.IdempotencyKey, digest); err != nil || found {
		return receipt, err
	}
	proposal, err := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if proposal.Version != command.ExpectedProposalVersion {
		return ports.CommitReceipt{}, model.ErrVersionConflict
	}
	next, events, err := proposal.Reject(command.ActorPersonaID, f.now())
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	return f.commit(ctx, command.ExpectedProposalVersion, next, events, command.IdempotencyKey, digest)
}

func (f *Facade) Get(
	ctx context.Context,
	proposalID string,
	actorPersonaID string,
) (model.ProfileUpdateProposal, error) {
	proposal, err := f.reader.Get(ctx, proposalID)
	if err != nil {
		return model.ProfileUpdateProposal{}, err
	}
	if strings.TrimSpace(actorPersonaID) == "" || proposal.PersonaID != actorPersonaID {
		return model.ProfileUpdateProposal{}, model.ErrForbidden
	}
	return proposal, nil
}

func (f *Facade) ListByPersona(
	ctx context.Context,
	personaID string,
	actorPersonaID string,
	cursor *ports.Cursor,
	limit int,
) (ports.Slice, error) {
	if strings.TrimSpace(actorPersonaID) == "" || personaID != actorPersonaID {
		return ports.Slice{}, model.ErrForbidden
	}
	return f.reader.ListByPersona(ctx, personaID, cursor, limit)
}

func (f *Facade) loadOwned(ctx context.Context, proposalID, actorPersonaID string) (model.ProfileUpdateProposal, error) {
	proposal, err := f.store.Load(ctx, proposalID)
	if err != nil {
		return model.ProfileUpdateProposal{}, err
	}
	if strings.TrimSpace(actorPersonaID) == "" || proposal.PersonaID != actorPersonaID {
		return model.ProfileUpdateProposal{}, model.ErrForbidden
	}
	return proposal, nil
}

func (f *Facade) commit(
	ctx context.Context,
	expectedVersion int64,
	proposal model.ProfileUpdateProposal,
	events []model.Event,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, error) {
	return f.store.Commit(ctx, expectedVersion, ports.ChangeSet{
		Proposal: proposal, Events: events, IdempotencyKey: idempotencyKey,
		CommandDigest: commandDigest,
	})
}

func commandDigest(command any) (string, error) {
	payload, err := json.Marshal(command)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return fmt.Sprintf("%x", digest[:]), nil
}
