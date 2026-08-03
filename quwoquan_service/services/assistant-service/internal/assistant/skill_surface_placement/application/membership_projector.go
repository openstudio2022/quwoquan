package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/ports"
)

const (
	AssistantConversationMemberAdded   = "ConversationMemberAdded"
	AssistantConversationMemberRemoved = "ConversationMemberRemoved"
)

type AssistantMembershipChange struct {
	EventID        string
	EventType      string
	ConversationID string
	ActorAccountID string
	ActorPersonaID string
	OccurredAt     time.Time
}

// MembershipProjector consumes only Chat's durable assistant-membership
// outbox stream. It provisions the default all_shared_eligible policy when the
// one Xiaoqu member joins and archives it when Xiaoqu leaves. Admin changes use
// CommandFacade; this projector never overwrites an existing active policy.
type MembershipProjector struct {
	store ports.Store
	now   func() time.Time
}

func NewMembershipProjector(
	store ports.Store,
	now func() time.Time,
) *MembershipProjector {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &MembershipProjector{store: store, now: now}
}

func (projector *MembershipProjector) Apply(
	ctx context.Context,
	change AssistantMembershipChange,
) error {
	if projector == nil || projector.store == nil {
		return model.ErrStorageUnavailable
	}
	change.EventID = strings.TrimSpace(change.EventID)
	change.EventType = strings.TrimSpace(change.EventType)
	change.ConversationID = strings.TrimSpace(change.ConversationID)
	change.ActorAccountID = strings.TrimSpace(change.ActorAccountID)
	change.ActorPersonaID = strings.TrimSpace(change.ActorPersonaID)
	if change.OccurredAt.IsZero() {
		change.OccurredAt = projector.now()
	}
	if change.EventID == "" || change.ConversationID == "" ||
		change.ActorAccountID == "" || change.ActorPersonaID == "" ||
		(change.EventType != AssistantConversationMemberAdded &&
			change.EventType != AssistantConversationMemberRemoved) {
		return model.ErrInvalidArgument
	}
	current, err := projector.store.Get(
		ctx,
		model.SurfaceConversation,
		change.ConversationID,
	)
	switch change.EventType {
	case AssistantConversationMemberAdded:
		if err == nil {
			return nil
		}
		if !errors.Is(err, model.ErrNotFound) {
			return err
		}
		command, commandErr := model.NewPutCommand(model.PutInput{
			SurfaceKind:      model.SurfaceConversation,
			SurfaceID:        change.ConversationID,
			ActorAccountID:   change.ActorAccountID,
			ActorPersonaID:   change.ActorPersonaID,
			Policy:           model.PolicyAllSharedEligible,
			DisabledSkillIDs: []string{},
			Status:           model.StatusActive,
			ExpectedRevision: 0,
			IdempotencyKey:   change.EventID,
			OccurredAt:       change.OccurredAt,
		})
		if commandErr != nil {
			return commandErr
		}
		if _, applyErr := projector.store.Apply(ctx, command); applyErr != nil {
			if errors.Is(applyErr, model.ErrRevisionConflict) {
				_, readErr := projector.store.Get(
					ctx,
					model.SurfaceConversation,
					change.ConversationID,
				)
				return readErr
			}
			return applyErr
		}
		return nil
	case AssistantConversationMemberRemoved:
		if errors.Is(err, model.ErrNotFound) {
			return nil
		}
		if err != nil {
			return err
		}
		if current.Status == model.StatusArchived {
			return nil
		}
		command, commandErr := model.NewPutCommand(model.PutInput{
			SurfaceKind:      current.SurfaceKind,
			SurfaceID:        current.SurfaceID,
			ActorAccountID:   change.ActorAccountID,
			ActorPersonaID:   change.ActorPersonaID,
			Policy:           current.Policy,
			DisabledSkillIDs: append([]string(nil), current.DisabledSkillIDs...),
			Status:           model.StatusArchived,
			ExpectedRevision: current.Revision,
			IdempotencyKey:   change.EventID,
			OccurredAt:       change.OccurredAt,
		})
		if commandErr != nil {
			return commandErr
		}
		_, applyErr := projector.store.Apply(ctx, command)
		return applyErr
	default:
		return model.ErrInvalidArgument
	}
}
