package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	circleerrors "quwoquan_service/services/circle-service/generated/circle_management/circle"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const receiptRetention = 7 * 24 * time.Hour

type CreateCommand struct {
	Title       string
	Description string
	TargetRef   model.TargetRef
	StartAt     time.Time
	EndAt       time.Time
	Capacity    int64
	JoinPolicy  model.JoinPolicy
}

type ParticipantCommand struct {
	GatheringID          string
	ParticipantPersonaID string
}

type GatheringCommand struct {
	GatheringID string
}

type CommandResult struct {
	GatheringID      string                 `json:"gatheringId"`
	Version          int64                  `json:"version"`
	Status           model.Status           `json:"status"`
	ParticipantState model.ParticipantState `json:"participantState,omitempty"`
	ConversationID   string                 `json:"conversationId,omitempty"`
	IdempotentReplay bool                   `json:"idempotentReplay"`
}

type Slice struct {
	GatheringID      string              `json:"gatheringId"`
	Version          int64               `json:"version"`
	CreatorPersonaID string              `json:"creatorPersonaId"`
	Title            string              `json:"title"`
	Description      string              `json:"description,omitempty"`
	TargetRef        model.TargetRef     `json:"targetRef"`
	StartAt          time.Time           `json:"startAt"`
	EndAt            time.Time           `json:"endAt,omitempty"`
	Capacity         int64               `json:"capacity"`
	JoinPolicy       model.JoinPolicy    `json:"joinPolicy"`
	Status           model.Status        `json:"status"`
	ConversationID   string              `json:"conversationId,omitempty"`
	ParticipantCount int64               `json:"participantCount"`
	Participants     []model.Participant `json:"participants"`
	CreatedAt        time.Time           `json:"createdAt"`
	UpdatedAt        time.Time           `json:"updatedAt"`
}

type CommandFacade struct {
	store         ports.AggregateStore
	targets       ports.TargetReader
	conversations ports.ConversationPort
	now           func() time.Time
}

func NewCommandFacade(store ports.AggregateStore, targets ports.TargetReader, conversations ports.ConversationPort) *CommandFacade {
	if store == nil || targets == nil || conversations == nil {
		panic("Gathering CommandFacade requires aggregate Store, TargetReader and ConversationPort")
	}
	return &CommandFacade{store: store, targets: targets, conversations: conversations, now: time.Now}
}

func (facade *CommandFacade) Create(ctx context.Context, command CreateCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	if err := facade.targets.RequireNavigable(ctx, command.TargetRef); err != nil {
		if errors.Is(err, ports.ErrTargetNotNavigable) {
			return CommandResult{}, circleerrors.AppErrorFromInvalidArgument("Gathering target is not navigable: " + err.Error())
		}
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringTargetUnavailable(err.Error())
	}
	gatheringID := stableID(actorID, current.IdempotencyKey)
	digest, err := commandDigest(actorID, "create", command)
	if err != nil {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	receipt, err := facade.commit(ctx, ports.CommitRequest{
		GatheringID: gatheringID, ReceiptKey: receiptKey(actorID, current.IdempotencyKey),
		CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(receiptRetention),
		EventType: "GatheringCreated",
		Mutate: func(existing *model.Gathering) (model.Gathering, error) {
			if existing != nil {
				return model.Gathering{}, ports.ErrVersionConflict
			}
			return model.Create(model.CreateInput{
				ID: gatheringID, CreatorPersonaID: actorID, Title: command.Title,
				Description: command.Description, TargetRef: command.TargetRef,
				StartAt: command.StartAt, EndAt: command.EndAt, Capacity: command.Capacity,
				JoinPolicy: command.JoinPolicy, OccurredAt: facade.now().UTC(),
			})
		},
	})
	if err != nil {
		return CommandResult{}, err
	}
	bound, err := facade.ensureConversationBound(ctx, receipt.Gathering, current.IdempotencyKey)
	if err != nil {
		return CommandResult{}, err
	}
	return resultFrom(bound, "", receipt.Replayed), nil
}

func (facade *CommandFacade) Join(ctx context.Context, command GatheringCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	requested, replayed, err := facade.mutate(ctx, actorID, current.IdempotencyKey, "join-request", command, command.GatheringID, "GatheringParticipantStateChanged", func(existing *model.Gathering) (model.Gathering, error) {
		if existing == nil {
			return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
		}
		return model.RequestJoin(*existing, actorID, facade.now().UTC())
	})
	if err != nil {
		return CommandResult{}, err
	}
	if requested.JoinPolicy == model.JoinPolicyApproval || participantState(requested, actorID) == model.ParticipantStateJoined {
		return resultFrom(requested, actorID, replayed), nil
	}
	if err := facade.conversations.ProjectParticipant(ctx, requested.ID, requested.CreatorPersonaID, actorID, "joined", membershipSourceSequence(requested.Version), "gathering:"+requested.ID+":join:"+actorID); err != nil {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringConversationBindingFailed(err.Error())
	}
	confirmed, _, err := facade.mutate(ctx, actorID, current.IdempotencyKey+":confirm", "join-confirm", command, command.GatheringID, "GatheringParticipantStateChanged", func(existing *model.Gathering) (model.Gathering, error) {
		if existing == nil {
			return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
		}
		return model.ConfirmJoin(*existing, actorID, facade.now().UTC())
	})
	if err != nil {
		return CommandResult{}, err
	}
	return resultFrom(confirmed, actorID, replayed), nil
}

func (facade *CommandFacade) Approve(ctx context.Context, command ParticipantCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	gathering, found, err := facade.store.Load(ctx, strings.TrimSpace(command.GatheringID))
	if err != nil {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	if !found {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering not found")
	}
	if actorID != gathering.CreatorPersonaID {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringPermissionDenied("Gathering creator is required")
	}
	participantID := strings.TrimSpace(command.ParticipantPersonaID)
	if err := facade.conversations.ProjectParticipant(ctx, gathering.ID, gathering.CreatorPersonaID, participantID, "joined", membershipSourceSequence(gathering.Version), "gathering:"+gathering.ID+":approve:"+participantID); err != nil {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringConversationBindingFailed(err.Error())
	}
	approved, replayed, err := facade.mutate(ctx, actorID, current.IdempotencyKey, "approve", command, gathering.ID, "GatheringParticipantStateChanged", func(existing *model.Gathering) (model.Gathering, error) {
		if existing == nil {
			return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
		}
		return model.Approve(*existing, actorID, participantID, facade.now().UTC())
	})
	if err != nil {
		return CommandResult{}, err
	}
	return resultFrom(approved, participantID, replayed), nil
}

func (facade *CommandFacade) Leave(ctx context.Context, command GatheringCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	left, replayed, err := facade.mutate(ctx, actorID, current.IdempotencyKey, "leave", command, command.GatheringID, "GatheringParticipantStateChanged", func(existing *model.Gathering) (model.Gathering, error) {
		if existing == nil {
			return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
		}
		return model.Leave(*existing, actorID, facade.now().UTC())
	})
	if err != nil {
		return CommandResult{}, err
	}
	if err := facade.conversations.ProjectParticipant(ctx, left.ID, left.CreatorPersonaID, actorID, "left", membershipSourceSequence(left.Version), "gathering:"+left.ID+":leave:"+actorID); err != nil {
		return CommandResult{}, gatheringerrors.AppErrorFromGatheringConversationBindingFailed(err.Error())
	}
	return resultFrom(left, actorID, replayed), nil
}

func (facade *CommandFacade) Cancel(ctx context.Context, command GatheringCommand) (CommandResult, error) {
	return facade.terminal(ctx, "cancel", "GatheringCancelled", command, model.Cancel)
}

func (facade *CommandFacade) Complete(ctx context.Context, command GatheringCommand) (CommandResult, error) {
	return facade.terminal(ctx, "complete", "GatheringCompleted", command, model.Complete)
}

func (facade *CommandFacade) terminal(ctx context.Context, operationName, eventType string, command GatheringCommand, apply func(model.Gathering, string, time.Time) (model.Gathering, error)) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	next, replayed, err := facade.mutate(ctx, actorID, current.IdempotencyKey, operationName, command, command.GatheringID, eventType, func(existing *model.Gathering) (model.Gathering, error) {
		if existing == nil {
			return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
		}
		return apply(*existing, actorID, facade.now().UTC())
	})
	if err != nil {
		return CommandResult{}, err
	}
	return resultFrom(next, "", replayed), nil
}

func (facade *CommandFacade) ensureConversationBound(ctx context.Context, current model.Gathering, requestKey string) (model.Gathering, error) {
	if current.Status != model.StatusDraft && current.ConversationID != "" {
		return current, nil
	}
	conversationID, err := facade.conversations.EnsureGroupConversation(ctx, current.ID, current.Title, current.CreatorPersonaID, current.Capacity, "gathering:"+current.ID+":conversation")
	if err != nil {
		_, _, _ = facade.mutate(ctx, current.CreatorPersonaID, requestKey+":binding-failed", "binding-failed", current.ID, current.ID, "GatheringConversationBindingFailed", func(existing *model.Gathering) (model.Gathering, error) {
			if existing == nil {
				return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
			}
			return model.MarkConversationBindingFailed(*existing, facade.now().UTC())
		})
		return model.Gathering{}, gatheringerrors.AppErrorFromGatheringConversationBindingFailed(err.Error())
	}
	bound, _, err := facade.mutate(ctx, current.CreatorPersonaID, requestKey+":binding:"+conversationID, "binding", conversationID, current.ID, "GatheringConversationBound", func(existing *model.Gathering) (model.Gathering, error) {
		if existing == nil {
			return model.Gathering{}, gatheringerrors.ErrGatheringNotFound
		}
		return model.BindConversation(*existing, conversationID, facade.now().UTC())
	})
	return bound, err
}

func (facade *CommandFacade) mutate(ctx context.Context, actorID, key, operationName string, payload any, gatheringID, eventType string, mutation ports.Mutation) (model.Gathering, bool, error) {
	digest, err := commandDigest(actorID, operationName, payload)
	if err != nil {
		return model.Gathering{}, false, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	receipt, err := facade.commit(ctx, ports.CommitRequest{
		GatheringID: strings.TrimSpace(gatheringID), ReceiptKey: receiptKey(actorID, key),
		CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(receiptRetention),
		EventType: eventType, Mutate: mutation,
	})
	return receipt.Gathering, receipt.Replayed, err
}

func (facade *CommandFacade) commit(ctx context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	receipt, err := facade.store.Commit(ctx, request)
	if err == nil {
		return receipt, nil
	}
	return ports.CommitReceipt{}, mapError(err)
}

type QueryFacade struct {
	store ports.AggregateStore
}

func NewQueryFacade(store ports.AggregateStore) *QueryFacade {
	if store == nil {
		panic("Gathering QueryFacade requires AggregateStore")
	}
	return &QueryFacade{store: store}
}

func (facade *QueryFacade) Get(ctx context.Context, gatheringID string) (Slice, error) {
	value, found, err := facade.store.Load(ctx, strings.TrimSpace(gatheringID))
	if err != nil {
		return Slice{}, gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
	if !found {
		return Slice{}, gatheringerrors.AppErrorFromGatheringNotFound("Gathering not found")
	}
	return sliceFrom(model.Reevaluate(value, time.Now().UTC())), nil
}

func resultFrom(value model.Gathering, participantPersonaID string, replayed bool) CommandResult {
	return CommandResult{
		GatheringID: value.ID, Version: value.Version, Status: value.Status,
		ParticipantState: participantState(value, participantPersonaID),
		ConversationID:   value.ConversationID, IdempotentReplay: replayed,
	}
}

func sliceFrom(value model.Gathering) Slice {
	return Slice{
		GatheringID: value.ID, Version: value.Version, CreatorPersonaID: value.CreatorPersonaID,
		Title: value.Title, Description: value.Description, TargetRef: value.TargetRef,
		StartAt: value.StartAt, EndAt: value.EndAt, Capacity: value.Capacity,
		JoinPolicy: value.JoinPolicy, Status: value.Status, ConversationID: value.ConversationID,
		ParticipantCount: model.JoinedCount(value), Participants: append([]model.Participant(nil), value.Participants...),
		CreatedAt: value.CreatedAt, UpdatedAt: value.UpdatedAt,
	}
}

func participantState(value model.Gathering, personaID string) model.ParticipantState {
	for _, participant := range value.Participants {
		if participant.PersonaID == strings.TrimSpace(personaID) {
			return participant.State
		}
	}
	return model.ParticipantState("")
}

func trustedCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", circleerrors.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func stableID(actorID, key string) string {
	digest := sha256.Sum256([]byte("gathering\x00" + actorID + "\x00" + key))
	return "gathering_" + hex.EncodeToString(digest[:12])
}

func receiptKey(actorID, key string) string {
	return actorID + ":" + strings.TrimSpace(key)
}

func membershipSourceSequence(aggregateVersion int64) int64 {
	return aggregateVersion * 10
}

func commandDigest(actorID, operationName string, payload any) (string, error) {
	encoded, err := json.Marshal(struct {
		ActorID       string `json:"actorId"`
		OperationName string `json:"operation"`
		Payload       any    `json:"payload"`
	}{actorID, operationName, payload})
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func mapError(err error) error {
	switch {
	case errors.Is(err, gatheringerrors.ErrGatheringNotFound):
		return gatheringerrors.AppErrorFromGatheringNotFound(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringNotOpen):
		return gatheringerrors.AppErrorFromGatheringNotOpen(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringFull):
		return gatheringerrors.AppErrorFromGatheringFull(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringPermissionDenied):
		return gatheringerrors.AppErrorFromGatheringPermissionDenied(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringParticipantStateInvalid):
		return gatheringerrors.AppErrorFromGatheringParticipantStateInvalid(err.Error())
	case errors.Is(err, gatheringerrors.ErrGatheringIdempotencyConflict):
		return gatheringerrors.AppErrorFromGatheringIdempotencyConflict(err.Error())
	case errors.Is(err, ports.ErrVersionConflict):
		return gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return circleerrors.AppErrorFromInvalidArgument(err.Error())
	default:
		return gatheringerrors.AppErrorFromGatheringStorageFailed(err.Error())
	}
}
