package profile_update_proposal

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
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
	ProposalID     string
	ActorPersonaID string
	IdempotencyKey string
}

type ApplyCommand struct {
	ProposalID     string
	ActorPersonaID string
	IdempotencyKey string
}

type RejectCommand struct {
	ProposalID     string
	ActorPersonaID string
	IdempotencyKey string
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
	for attempt := 0; attempt < 3; attempt++ {
		proposal, loadErr := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
		if loadErr != nil {
			return ports.CommitReceipt{}, loadErr
		}
		switch proposal.Status {
		case model.StatusConfirmed, model.StatusApplying, model.StatusApplied:
			return f.recordNoopReceipt(
				ctx,
				proposal,
				command.IdempotencyKey,
				digest,
			)
		case model.StatusPending:
		default:
			return ports.CommitReceipt{}, model.ErrInvalidTransition
		}
		targetVersion, versionErr := f.personaReader.CurrentVersion(ctx, proposal.PersonaID)
		if versionErr != nil {
			return ports.CommitReceipt{}, versionErr
		}
		next, events, confirmErr := proposal.Confirm(
			command.ActorPersonaID,
			targetVersion,
			f.now(),
		)
		if confirmErr != nil {
			return ports.CommitReceipt{}, confirmErr
		}
		receipt, commitErr := f.commit(
			ctx,
			proposal.Version,
			next,
			events,
			command.IdempotencyKey,
			digest,
		)
		if commitErr == nil {
			return receipt, nil
		}
		if !errors.Is(commitErr, model.ErrVersionConflict) || attempt == 2 {
			return ports.CommitReceipt{}, commitErr
		}
	}
	panic("unreachable profile proposal confirm retry")
}

func (f *Facade) Apply(ctx context.Context, command ApplyCommand) (ports.CommitReceipt, error) {
	digest, err := commandDigest(command)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := f.store.Replay(ctx, command.ProposalID, command.IdempotencyKey, digest); err != nil || found {
		return receipt, err
	}
	proposal, err := f.claimApply(ctx, command, digest)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if proposal.Status == model.StatusApplied {
		return f.recordNoopReceipt(
			ctx,
			proposal,
			command.IdempotencyKey,
			digest,
		)
	}
	if proposal.TargetPersonaExpectedVersion == nil {
		return ports.CommitReceipt{}, model.ErrInvalidTransition
	}
	if err := f.personaWriter.ApplyProfileProposal(ctx, personaports.ApplyProfileProposalCommand{
		ProposalID:             proposal.ID,
		PersonaID:              proposal.PersonaID,
		ExpectedPersonaVersion: *proposal.TargetPersonaExpectedVersion,
		Changes:                proposal.ProposedChanges,
	}); err != nil {
		if errors.Is(err, personamodel.ErrVersionConflict) {
			if expireErr := f.expireApply(ctx, command, digest); expireErr != nil {
				return ports.CommitReceipt{}, expireErr
			}
		}
		return ports.CommitReceipt{}, err
	}
	for attempt := 0; attempt < 3; attempt++ {
		current, loadErr := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
		if loadErr != nil {
			return ports.CommitReceipt{}, loadErr
		}
		if current.Status == model.StatusApplied {
			return f.recordNoopReceipt(
				ctx,
				current,
				command.IdempotencyKey,
				digest,
			)
		}
		if current.Status != model.StatusApplying {
			return ports.CommitReceipt{}, model.ErrInvalidTransition
		}
		next, events, applyErr := current.MarkApplied(f.now())
		if applyErr != nil {
			return ports.CommitReceipt{}, applyErr
		}
		receipt, commitErr := f.commit(
			ctx,
			current.Version,
			next,
			events,
			command.IdempotencyKey,
			digest,
		)
		if commitErr == nil {
			return receipt, nil
		}
		if !errors.Is(commitErr, model.ErrVersionConflict) || attempt == 2 {
			return ports.CommitReceipt{}, commitErr
		}
	}
	panic("unreachable profile proposal apply retry")
}

func (f *Facade) Reject(ctx context.Context, command RejectCommand) (ports.CommitReceipt, error) {
	digest, err := commandDigest(command)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := f.store.Replay(ctx, command.ProposalID, command.IdempotencyKey, digest); err != nil || found {
		return receipt, err
	}
	for attempt := 0; attempt < 3; attempt++ {
		proposal, loadErr := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
		if loadErr != nil {
			return ports.CommitReceipt{}, loadErr
		}
		if proposal.Status == model.StatusRejected {
			return f.recordNoopReceipt(
				ctx,
				proposal,
				command.IdempotencyKey,
				digest,
			)
		}
		if proposal.Status != model.StatusPending && proposal.Status != model.StatusConfirmed {
			return ports.CommitReceipt{}, model.ErrInvalidTransition
		}
		next, events, rejectErr := proposal.Reject(command.ActorPersonaID, f.now())
		if rejectErr != nil {
			return ports.CommitReceipt{}, rejectErr
		}
		receipt, commitErr := f.commit(
			ctx,
			proposal.Version,
			next,
			events,
			command.IdempotencyKey,
			digest,
		)
		if commitErr == nil {
			return receipt, nil
		}
		if !errors.Is(commitErr, model.ErrVersionConflict) || attempt == 2 {
			return ports.CommitReceipt{}, commitErr
		}
	}
	panic("unreachable profile proposal reject retry")
}

func (f *Facade) claimApply(
	ctx context.Context,
	command ApplyCommand,
	commandDigest string,
) (model.ProfileUpdateProposal, error) {
	for attempt := 0; attempt < 3; attempt++ {
		proposal, err := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
		if err != nil {
			return model.ProfileUpdateProposal{}, err
		}
		switch proposal.Status {
		case model.StatusApplying, model.StatusApplied:
			return proposal, nil
		case model.StatusConfirmed:
		default:
			return model.ProfileUpdateProposal{}, model.ErrInvalidTransition
		}
		next, events, err := proposal.BeginApply(f.now())
		if err != nil {
			return model.ProfileUpdateProposal{}, err
		}
		_, err = f.commit(
			ctx,
			proposal.Version,
			next,
			events,
			phaseReceiptKey(command.IdempotencyKey, "claim"),
			phaseDigest(commandDigest, "claim"),
		)
		if err == nil {
			return next, nil
		}
		if !errors.Is(err, model.ErrVersionConflict) || attempt == 2 {
			return model.ProfileUpdateProposal{}, err
		}
	}
	panic("unreachable profile proposal apply claim retry")
}

func (f *Facade) expireApply(
	ctx context.Context,
	command ApplyCommand,
	commandDigest string,
) error {
	for attempt := 0; attempt < 3; attempt++ {
		proposal, err := f.loadOwned(ctx, command.ProposalID, command.ActorPersonaID)
		if err != nil {
			return err
		}
		if proposal.Status == model.StatusExpired {
			return nil
		}
		if proposal.Status != model.StatusApplying {
			return model.ErrInvalidTransition
		}
		next, events, err := proposal.ExpireApply(f.now())
		if err != nil {
			return err
		}
		_, err = f.commit(
			ctx,
			proposal.Version,
			next,
			events,
			phaseReceiptKey(command.IdempotencyKey, "expire"),
			phaseDigest(commandDigest, "expire"),
		)
		if err == nil {
			return nil
		}
		if !errors.Is(err, model.ErrVersionConflict) || attempt == 2 {
			return err
		}
	}
	panic("unreachable profile proposal apply expiry retry")
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

func (f *Facade) recordNoopReceipt(
	ctx context.Context,
	proposal model.ProfileUpdateProposal,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, error) {
	return f.store.RecordNoopReceipt(
		ctx,
		proposal,
		idempotencyKey,
		commandDigest,
	)
}

func commandDigest(command any) (string, error) {
	payload, err := json.Marshal(command)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return fmt.Sprintf("%x", digest[:]), nil
}

func phaseReceiptKey(idempotencyKey, phase string) string {
	digest := sha256.Sum256([]byte(idempotencyKey + "\x00" + phase))
	return fmt.Sprintf("profile-proposal-%s-%x", phase, digest[:16])
}

func phaseDigest(commandDigest, phase string) string {
	digest := sha256.Sum256([]byte(commandDigest + "\x00" + phase))
	return fmt.Sprintf("%x", digest[:])
}
